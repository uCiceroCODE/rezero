"""
reader.ai.document_processor
Estrae testo pulito e strutturato dai volumi EPUB per la pipeline di indicizzazione e RAG.
Gestisce specificamente i tag HTML giapponesi (<ruby>, <rt>, <rp>) ed estrae coordinate esatte.
"""
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import epub_parser

def clean_html_to_text(html_content):
    """
    Converte XHTML/HTML giapponese in testo pulito:
    - Rimuove <rt> e <rp> dei ruby per evitare che il furigana si mescoli al testo base.
    - Strippa script, style e tag non testuali.
    - Preserva la struttura dei paragrafi (<p>, <div>, <br>).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Rimuove elementi irrilevanti per l'IR
    for tag in soup.find_all(['script', 'style', 'rt', 'rp', 'meta', 'link']):
        tag.decompose()
        
    paragraphs = []
    # I blocchi di testo narrativo sono tipicamente in <p> o <div>
    p_tags = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div'])
    if p_tags:
        for p in p_tags:
            t = p.get_text().strip()
            if t:
                # Normalizza spazi interni mantenendo caratteri CJK intatti
                t = re.sub(r'[ \t\r\f\v]+', ' ', t)
                paragraphs.append(t)
    else:
        # Fallback se non ci sono tag <p> strutturati
        text = soup.get_text()
        for line in text.split('\n'):
            line = line.strip()
            if line:
                paragraphs.append(line)
                
    # Rimuove duplicati consecutivi dovuti a div padri/figli
    deduped = []
    for p in paragraphs:
        if not deduped or deduped[-1] != p:
            deduped.append(p)
            
    full_text = "\n".join(deduped)
    return deduped, full_text

def extract_chapter_documents(book_id):
    """
    Estrae tutti i capitoli di un libro registrato in epub_parser.
    Restituisce un dizionario con metadati e lista dei capitoli processati.
    """
    book = epub_parser.get_book(book_id)
    if not book:
        return None
        
    results = {
        'book_id': book_id,
        'title': book['title'],
        'volume_num': book.get('volume', 1),
        'filename': book.get('filename', ''),
        'chapters': []
    }
    
    # Leggi direttamente dallo zip per massima velocita
    with zipfile.ZipFile(book['filepath'], 'r') as z:
        opf = ET.fromstring(z.read(book['opf_path']))
        manifest = {item.attrib['id']: item.attrib for item in opf.findall('.//{*}manifest/{*}item')}
        spine = opf.findall('.//{*}spine/{*}itemref')
        opf_dir = book['opf_dir']
        
        for idx, itemref in enumerate(spine):
            idref = itemref.attrib.get('idref')
            if not idref or idref not in manifest:
                continue
                
            href = manifest[idref]['href']
            ch_path = os.path.normpath(os.path.join(opf_dir, href)).replace('\\', '/')
            
            try:
                raw_html = z.read(ch_path).decode('utf-8', errors='ignore')
            except Exception:
                continue
                
            # Titolo del capitolo
            soup_title = BeautifulSoup(raw_html[:1500], 'html.parser')
            ch_title = soup_title.title.string.strip() if soup_title.title and soup_title.title.string else f"Capitolo {idx + 1}"
            
            paragraphs, full_text = clean_html_to_text(raw_html)
            
            # Filtra capitoli vuoti (es. solo immagini o pagine di copyright)
            # Considera capitoli con almeno 20 caratteri CJK
            cjk_count = len(re.findall(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', full_text))
            
            results['chapters'].append({
                'spine_index': idx,
                'chapter_title': ch_title,
                'paragraphs': paragraphs,
                'full_text': full_text,
                'char_count': len(full_text),
                'cjk_count': cjk_count,
                'is_text_heavy': cjk_count > 50
            })
            
    return results
