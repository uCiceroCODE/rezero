import sqlite3
import os
import re
import urllib.request
import urllib.parse
import json

DICT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reader_data', 'edict.db')

# Common deinflection rules for Japanese verbs and adjectives
DEINFLECT_RULES = [
    # Ichidan past / te
    ('た', 'る'),
    ('て', 'る'),
    ('だ', 'る'),
    ('で', 'る'),
    ('ない', 'る'),
    ('なかった', 'る'),
    ('られる', 'る'),
    ('させる', 'る'),
    ('よう', 'る'),
    
    # Godan past / te / conditional
    ('いた', 'く'),
    ('いて', 'く'),
    ('いだ', 'ぐ'),
    ('いで', 'ぐ'),
    ('した', 'す'),
    ('して', 'す'),
    ('った', 'う'),
    ('って', 'う'),
    ('った', 'つ'),
    ('って', 'つ'),
    ('った', 'る'),
    ('って', 'る'),
    ('んだ', 'む'),
    ('んで', 'む'),
    ('んだ', 'ぶ'),
    ('んで', 'ぶ'),
    ('んだ', 'ぬ'),
    ('んで', 'ぬ'),
    
    # Negative godan
    ('かない', 'く'),
    ('がない', 'ぐ'),
    ('さない', 'す'),
    ('たない', 'つ'),
    ('なない', 'ぬ'),
    ('まない', 'む'),
    ('らない', 'る'),
    ('わない', 'う'),
    ('ばない', 'ぶ'),

    # Polite masu forms
    ('ます', 'る'),
    ('ます', 'う'),
    ('ます', 'く'),
    ('ます', 'ぐ'),
    ('ます', 'す'),
    ('ます', 'つ'),
    ('ます', 'ぬ'),
    ('ます', 'ぶ'),
    ('ます', 'む'),
    ('ました', 'る'),
    ('ました', 'う'),
    ('ません', 'る'),
    ('ません', 'う'),
    
    # Adjectives (-i)
    ('くない', 'い'),
    ('くなかった', 'い'),
    ('かった', 'い'),
    ('くて', 'い'),
    ('く', 'い'),
    ('さ', 'い'),
    
    # Potential / Passive
    ('える', 'う'),
    ('ける', 'く'),
    ('げる', 'ぐ'),
    ('せる', 'す'),
    ('てる', 'つ'),
    ('ねる', 'ぬ'),
    ('べる', 'ぶ'),
    ('める', 'む'),
    ('れる', 'る'),
]

def get_dict_conn():
    if not os.path.exists(DICT_DB_PATH):
        return None
    conn = sqlite3.connect(DICT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def clean_gloss(gloss_raw):
    # Splits gloss into readable English definitions list
    # e.g. "(n,adj-no) (1) seriousness/(2) truth" -> ["seriousness", "truth"]
    senses = []
    # remove EntL... tags
    gloss_raw = re.sub(r'EntL\d+X?', '', gloss_raw).strip()
    parts = [p.strip() for p in gloss_raw.split('/') if p.strip()]
    for p in parts:
        # strip tags like (n), (v5u), (1), (2), (See ...)
        clean = re.sub(r'^\([a-zA-Z0-9,\- ]+\)\s*', '', p)
        clean = re.sub(r'^\(\d+\)\s*', '', clean)
        clean = re.sub(r'\(See [^)]+\)', '', clean).strip()
        if clean and clean not in senses:
            senses.append(clean)
    return senses[:5]

def query_local_dict(term):
    conn = get_dict_conn()
    if not conn:
        return []
    
    try:
        rows = conn.execute('''
            SELECT e.kanji, e.reading, e.gloss 
            FROM lookup l 
            JOIN entries e ON l.entry_id = e.id 
            WHERE l.term = ? 
            LIMIT 5
        ''', (term,)).fetchall()
        
        results = []
        for r in rows:
            kanji_list = [k.strip() for k in r['kanji'].split(';') if k.strip()]
            reading_list = [rd.strip() for rd in r['reading'].split(';') if rd.strip()] if r['reading'] else []
            senses = clean_gloss(r['gloss'])
            results.append({
                'kanji': kanji_list[0] if kanji_list else term,
                'kanji_alt': kanji_list[1:],
                'reading': reading_list[0] if reading_list else (kanji_list[0] if kanji_list else term),
                'reading_alt': reading_list[1:],
                'definitions': senses,
                'source': 'local'
            })
        return results
    except Exception as e:
        print(f"Error querying local dict: {e}")
        return []
    finally:
        conn.close()

def deinflect(word):
    candidates = [word]
    for suffix, replacement in DEINFLECT_RULES:
        if word.endswith(suffix):
            base = word[:-len(suffix)] + replacement
            if base not in candidates and len(base) > 0:
                candidates.append(base)
    # Also test stripping common particles if attached
    for part in ['は', 'が', 'を', 'に', 'へ', 'と', 'で', 'から', 'まで', 'より', 'も']:
        if word.endswith(part) and len(word) > 1:
            candidates.append(word[:-len(part)])
    return candidates

def lookup_local(word):
    # Try exact word
    results = query_local_dict(word)
    if results:
        return results, word
    
    # Try deinflected forms
    candidates = deinflect(word)
    for c in candidates:
        if c == word:
            continue
        res = query_local_dict(c)
        if res:
            return res, c
            
    # Try prefix trimming (e.g. for compound words or punctuation attached)
    for l in range(len(word) - 1, 1, -1):
        sub = word[:l]
        res = query_local_dict(sub)
        if res:
            return res, sub
            
    return [], word

def query_jisho(word):
    url = f"https://jisho.org/api/v1/search/words?keyword={urllib.parse.quote(word)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            items = []
            for item in data.get('data', [])[:5]:
                jap = item.get('japanese', [{}])[0]
                senses = []
                for s in item.get('senses', []):
                    senses.extend(s.get('english_definitions', []))
                items.append({
                    'kanji': jap.get('word', jap.get('reading', word)),
                    'reading': jap.get('reading', ''),
                    'definitions': senses[:5],
                    'jlpt': item.get('jlpt', []),
                    'is_common': item.get('is_common', False),
                    'source': 'jisho'
                })
            return items
    except Exception as e:
        print(f"Jisho query error: {e}")
        return []

def full_lookup(word):
    word = word.strip()
    if not word:
        return {'term': '', 'found': False, 'results': [], 'matched_lemma': ''}
    
    # 1. Local dictionary lookup (fast, offline)
    local_results, lemma = lookup_local(word)
    if local_results:
        return {
            'term': word,
            'matched_lemma': lemma,
            'found': True,
            'results': local_results
        }
    
    # 2. Online Jisho lookup
    jisho_results = query_jisho(word)
    if jisho_results:
        return {
            'term': word,
            'matched_lemma': word,
            'found': True,
            'results': jisho_results
        }
        
    return {
        'term': word,
        'matched_lemma': word,
        'found': False,
        'results': []
    }
