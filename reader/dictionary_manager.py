import sqlite3
import os
import re
import html
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

# Punctuation to strip from lookup terms (compiled once)
_PUNCT_RE = re.compile(
    r'^[\s\.,!?、。！？…「」『』【】《》〝〟・〜（）\(\)\[\]\{\}<>"\'\'\'""]+|'
    r'[\s\.,!?、。！？…「」『』【】《》〝〟・〜（）\(\)\[\]\{\}<>"\'\'\'""]+$'
)

# EDICT tag pattern: e.g. (rK), (ik), (iK), (ok), (oK), (sk), (sK)
# These are field-type markers in EDICT entries that are not useful for display
_EDICT_TAG_RE = re.compile(r'\([a-zA-Z]{1,4}\)')

def _strip_edict_tags(text: str) -> tuple[str, list[str]]:
    """Remove EDICT tags from a kanji/reading field.
    Returns (cleaned_text, [tags_found]).
    """
    tags = _EDICT_TAG_RE.findall(text)
    cleaned = _EDICT_TAG_RE.sub('', text).strip()
    return cleaned, tags

def _clean_term(term: str) -> str:
    """Unescape HTML entities and strip surrounding punctuation/whitespace."""
    term = html.unescape(term)
    term = _PUNCT_RE.sub('', term)
    return term

def get_dict_conn():
    if not os.path.exists(DICT_DB_PATH):
        return None
    conn = sqlite3.connect(DICT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def clean_gloss(gloss_raw):
    senses = []
    gloss_raw = re.sub(r'EntL\d+X?', '', gloss_raw).strip()
    parts = [p.strip() for p in gloss_raw.split('/') if p.strip()]
    for p in parts:
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

            # Strip EDICT display tags from kanji and reading; collect them separately
            all_tags = []
            cleaned_kanji_list = []
            for k in kanji_list:
                ck, tags = _strip_edict_tags(k)
                if ck:
                    cleaned_kanji_list.append(ck)
                all_tags.extend(tags)
            cleaned_reading_list = []
            for rd in reading_list:
                crd, tags = _strip_edict_tags(rd)
                if crd:
                    cleaned_reading_list.append(crd)
                all_tags.extend(tags)
            # Deduplicate tags
            seen = set()
            unique_tags = [t for t in all_tags if not (t in seen or seen.add(t))]

            results.append({
                'kanji': cleaned_kanji_list[0] if cleaned_kanji_list else term,
                'kanji_alt': cleaned_kanji_list[1:],
                'reading': cleaned_reading_list[0] if cleaned_reading_list else (cleaned_kanji_list[0] if cleaned_kanji_list else term),
                'reading_alt': cleaned_reading_list[1:],
                'definitions': senses,
                'tags': unique_tags,  # raw EDICT tags, hidden in UI by default
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
    # Strip common particles if attached
    for part in ['は', 'が', 'を', 'に', 'へ', 'と', 'で', 'から', 'まで', 'より', 'も']:
        if word.endswith(part) and len(word) > 1:
            candidates.append(word[:-len(part)])
    return candidates

def lookup_local(word):
    # Clean first
    clean_word = _clean_term(word)
    if not clean_word:
        return [], word

    # 1. Exact match (cleaned)
    results = query_local_dict(clean_word)
    if results:
        return results, clean_word

    # 2. Deinflected forms
    for candidate in deinflect(clean_word):
        if candidate == clean_word:
            continue
        res = query_local_dict(candidate)
        if res:
            return res, candidate

    # 3. Prefix trimming (compound words)
    for length in range(len(clean_word) - 1, 1, -1):
        sub = clean_word[:length]
        res = query_local_dict(sub)
        if res:
            return res, sub

    return [], clean_word

def query_jisho(word):
    url = f"https://jisho.org/api/v1/search/words?keyword={urllib.parse.quote(word)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
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
    
    # 2. Online Jisho fallback
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
