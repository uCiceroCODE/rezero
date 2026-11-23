import os
import sys
from bs4 import BeautifulSoup

def sanitize_html_fragment(html_str):
    soup = BeautifulSoup(html_str, 'html.parser')
    
    # Strip executable/embedded tags
    for tag in soup.find_all(['script', 'iframe', 'object', 'embed', 'applet', 'base', 'form']):
        tag.decompose()

    # Strip dangerous inline events and javascript: URLs
    for el in soup.find_all():
        event_attrs = [k for k in el.attrs if k.lower().startswith('on')]
        for k in event_attrs:
            del el[k]
        for attr in ('href', 'src'):
            val = el.get(attr)
            if val and isinstance(val, str) and val.strip().lower().startswith(('javascript:', 'data:text/html')):
                del el[attr]
                
    return str(soup)

def test_sanitization():
    dirty = (
        '<div>'
        '<h1>Re:Zero</h1>'
        '<p>スバル「死に戻り」</p>'
        '<script>alert("XSS")</script>'
        '<img src="subaru.jpg" onerror="alert(1)">'
        '<a href="javascript:void(0)">Link malevolo</a>'
        '<iframe src="https://evil.com"></iframe>'
        '</div>'
    )
    clean = sanitize_html_fragment(dirty)
    
    assert '<script>' not in clean, "Script tag non rimosso!"
    assert '<iframe>' not in clean, "Iframe tag non rimosso!"
    assert 'onerror' not in clean, "Attributo onerror non rimosso!"
    assert 'javascript:' not in clean, "URL javascript: non rimosso!"
    assert 'スバル「死に戻り」' in clean, "Testo giapponese alterato o rimosso!"
    assert 'src="subaru.jpg"' in clean, "Immagine legittima rimossa!"
    print("✅ Test sanitizzazione completato con successo: tutti gli assert sono passati.")

if __name__ == '__main__':
    test_sanitization()
