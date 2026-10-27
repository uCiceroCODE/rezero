import requests
import urllib.parse
from database import get_cached_translation, set_cached_translation

def translate_google(text, target_lang='it'):
    url = 'https://translate.googleapis.com/translate_a/single'
    params = {
        'client': 'gtx',
        'sl': 'ja',
        'tl': target_lang,
        'dt': 't',
        'q': text
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, params=params, headers=headers, timeout=8)
    if resp.status_code == 200:
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
            translated = ''.join([part[0] for part in data[0] if part and part[0]])
            if translated:
                return translated.strip()
    return None

def translate_mymemory(text, target_lang='it'):
    try:
        from deep_translator import MyMemoryTranslator
        lang_pair_map = {'it': 'it-IT', 'en': 'en-GB'}
        tl = lang_pair_map.get(target_lang, 'it-IT')
        res = MyMemoryTranslator(source='ja-JP', target=tl).translate(text)
        if res:
            return res.strip()
    except Exception as e:
        print(f"MyMemory error: {e}")
    return None

def translate_text(text, target_lang='it'):
    text = text.strip()
    if not text:
        return {'success': False, 'translated': '', 'source': 'empty'}
    
    # 1. Check local DB cache
    cached = get_cached_translation(text, target_lang)
    if cached:
        return {'success': True, 'translated': cached, 'source': 'cache', 'target_lang': target_lang}
    
    # 2. Try Google Translate (gtx)
    try:
        gtx_res = translate_google(text, target_lang)
        if gtx_res:
            set_cached_translation(text, gtx_res, target_lang)
            return {'success': True, 'translated': gtx_res, 'source': 'google', 'target_lang': target_lang}
    except Exception as e:
        print(f"Google translate error: {e}")
        
    # 3. Fallback to MyMemory
    try:
        mm_res = translate_mymemory(text, target_lang)
        if mm_res:
            set_cached_translation(text, mm_res, target_lang)
            return {'success': True, 'translated': mm_res, 'source': 'mymemory', 'target_lang': target_lang}
    except Exception as e:
        print(f"MyMemory fallback error: {e}")

    return {'success': False, 'translated': 'Traduzione non disponibile al momento.', 'source': 'failed'}
