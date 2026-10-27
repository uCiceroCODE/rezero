import pykakasi
import re
from bs4 import BeautifulSoup, NavigableString

_kks = None

def get_kks():
    global _kks
    if _kks is None:
        _kks = pykakasi.kakasi()
    return _kks

def contains_kanji(text):
    return bool(re.search(r'[\u4e00-\u9faf\u3400-\u4dbf]', text))

def add_furigana_to_text(text):
    """
    Converts kanji in plain text to <ruby>Kanji<rt>reading</rt></ruby> tags.
    """
    if not contains_kanji(text):
        return text
    
    kks = get_kks()
    conv = kks.convert(text)
    out = []
    for item in conv:
        orig = item['orig']
        hira = item['hira']
        if contains_kanji(orig) and orig != hira:
            # If orig has mixed kanji and kana (e.g. 倒れ, 気付い),
            # pykakasi splits well, but we wrap in ruby
            out.append(f'<ruby>{orig}<rt>{hira}</rt></ruby>')
        else:
            out.append(orig)
    return ''.join(out)

def inject_furigana_into_html(html_str):
    """
    Takes an HTML fragment, finds text nodes outside existing <ruby> / <rt> / <script> / <style> tags,
    and replaces Kanji words with <ruby> markup.
    """
    soup = BeautifulSoup(html_str, 'html.parser')
    
    # Do not touch existing ruby elements or headers/scripts
    skip_tags = {'ruby', 'rt', 'rp', 'script', 'style', 'head', 'meta', 'link'}
    
    for text_node in list(soup.find_all(string=True)):
        if text_node.parent and text_node.parent.name in skip_tags:
            continue
        
        # Check if grandparent is ruby/rt
        parent = text_node.parent
        is_in_ruby = False
        while parent:
            if parent.name in ('ruby', 'rt', 'rp'):
                is_in_ruby = True
                break
            parent = parent.parent
        if is_in_ruby:
            continue

        raw = str(text_node)
        if contains_kanji(raw):
            new_html = add_furigana_to_text(raw)
            if new_html != raw:
                # Parse replacement fragment
                new_soup = BeautifulSoup(new_html, 'html.parser')
                text_node.replace_with(new_soup)
                
    return str(soup)

def analyze_tokens(text):
    kks = get_kks()
    conv = kks.convert(text)
    return [{
        'orig': item['orig'],
        'hira': item['hira'],
        'kana': item['kana'],
        'romaji': item['hepburn'],
        'has_kanji': contains_kanji(item['orig'])
    } for item in conv]
