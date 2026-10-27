import os
import glob
import re
import io
import hashlib
import zipfile
import mimetypes
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

BOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# In-memory cache for book metadata
_books_cache = {}
_last_epub_mtimes = {}

def check_mtimes_changed():
    global _last_epub_mtimes
    current_files = glob.glob(os.path.join(BOOKS_DIR, '*.epub'))
    current_mtimes = {f: os.path.getmtime(f) for f in current_files}
    if current_mtimes != _last_epub_mtimes:
        _last_epub_mtimes = current_mtimes
        return True
    return False

def normalize_digits(s):
    # Converts fullwidth Japanese digits ０-９ to standard 0-9
    return re.sub(r'[０-９]', lambda m: chr(ord(m.group(0)) - 0xFEE0), s)

def extract_volume_number(filename, title):
    norm_fn = normalize_digits(filename)
    norm_ti = normalize_digits(title)
    
    # Check filename patterns like "Re_ゼロから始める異世界生活1.epub" or "Re_ゼロから始める異世界生活 25" or "(7)"
    patterns = [
        r'異世界生活\s*[（(]?\s*(\d+)\s*[)）]?',
        r'vol\.?\s*(\d+)',
        r'volume\s*(\d+)',
        r'\b(\d+)\b'
    ]
    for pat in patterns:
        m = re.search(pat, norm_fn, re.IGNORECASE)
        if m:
            return int(m.group(1))
            
    for pat in patterns:
        m = re.search(pat, norm_ti, re.IGNORECASE)
        if m:
            return int(m.group(1))
            
    return 999

def get_book_id(filepath):
    # Short stable deterministic id based on filename
    rel = os.path.basename(filepath)
    return hashlib.md5(rel.encode('utf-8')).hexdigest()[:12]

def find_cover_href(z, opf_root):
    manifest = {}
    for item in opf_root.findall('.//{*}manifest/{*}item'):
        manifest[item.attrib['id']] = item.attrib
    
    # 1. properties='cover-image'
    for item in manifest.values():
        if 'cover-image' in item.get('properties', ''):
            return item['href']
            
    # 2. meta name='cover'
    for meta in opf_root.findall('.//{*}meta'):
        if meta.attrib.get('name') == 'cover':
            cover_id = meta.attrib.get('content')
            if cover_id in manifest:
                return manifest[cover_id]['href']
                
    # 3. id contains 'cover' and image
    for item in manifest.values():
        if 'cover' in item.get('id', '').lower() and item.get('media-type', '').startswith('image/'):
            return item['href']
            
    # 4. href contains 'cover' and image
    for item in manifest.values():
        if 'cover' in item.get('href', '').lower() and item.get('media-type', '').startswith('image/'):
            return item['href']
            
    # 5. First image in manifest
    for item in manifest.values():
        if item.get('media-type', '').startswith('image/'):
            return item['href']
            
    return None

def scan_books(force_reload=False):
    global _books_cache
    if _books_cache and not force_reload and not check_mtimes_changed():
        return list(_books_cache.values())
        
    books = {}
    epub_files = sorted(glob.glob(os.path.join(BOOKS_DIR, '*.epub')))
    
    for filepath in epub_files:
        if os.path.getsize(filepath) < 1024:
            continue # Skip 0-byte or incomplete download files

        book_id = get_book_id(filepath)
        filename = os.path.basename(filepath)
        size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)
        
        try:
            with zipfile.ZipFile(filepath, 'r') as z:
                c = z.read('META-INF/container.xml')
                root = ET.fromstring(c)
                opf_path = root.find('.//{*}rootfile').attrib['full-path']
                opf_dir = os.path.dirname(opf_path)
                opf_xml = z.read(opf_path)
                opf = ET.fromstring(opf_xml)
                
                title = opf.findtext('.//{*}title') or filename
                title = re.sub(r'<[^>]+>', '', title).strip()
                creator = opf.findtext('.//{*}creator') or '長月 達平'
                
                # Manifest map
                manifest = {}
                for item in opf.findall('.//{*}manifest/{*}item'):
                    manifest[item.attrib['id']] = item.attrib
                    
                # Spine items
                spine = []
                for itemref in opf.findall('.//{*}spine/{*}itemref'):
                    idref = itemref.attrib.get('idref')
                    if idref in manifest:
                        spine.append({
                            'id': idref,
                            'href': manifest[idref]['href']
                        })
                
                # Cover
                cover_href = find_cover_href(z, opf)
                if cover_href:
                    cover_full = os.path.normpath(os.path.join(opf_dir, cover_href)).replace('\\', '/')
                else:
                    cover_full = ''
                    
                volume_num = extract_volume_number(filename, title)
                
                books[book_id] = {
                    'id': book_id,
                    'filename': filename,
                    'filepath': filepath,
                    'title': title,
                    'creator': creator,
                    'volume': volume_num,
                    'size_mb': size_mb,
                    'total_spine': len(spine),
                    'cover_path': cover_full,
                    'opf_dir': opf_dir,
                    'opf_path': opf_path
                }
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
            
    # Sort books by volume number ascending
    sorted_books = sorted(books.values(), key=lambda b: (b['volume'], b['title']))
    _books_cache = {b['id']: b for b in sorted_books}
    return sorted_books

def get_book(book_id):
    if not _books_cache:
        scan_books()
    return _books_cache.get(book_id)

def validate_and_import_epub(file_bytes, original_filename):
    """
    Validates that file_bytes is a valid EPUB and is written in Japanese.
    If valid, saves it to BOOKS_DIR and reloads books list.
    """
    if not file_bytes:
        return {'success': False, 'error': 'Nessun file ricevuto o file vuoto.'}
        
    try:
        mem_zip = io.BytesIO(file_bytes)
        if not zipfile.is_zipfile(mem_zip):
            return {'success': False, 'error': 'Il file caricato non è un archivio EPUB valido.'}
            
        with zipfile.ZipFile(mem_zip, 'r') as z:
            names = z.namelist()
            if 'META-INF/container.xml' not in names:
                return {'success': False, 'error': 'Archivio EPUB non conforme: manca META-INF/container.xml.'}
                
            c = z.read('META-INF/container.xml')
            root = ET.fromstring(c)
            rootfile_el = root.find('.//{*}rootfile')
            if rootfile_el is None or 'full-path' not in rootfile_el.attrib:
                return {'success': False, 'error': 'Container EPUB privo del puntamento al package OPF.'}
                
            opf_path = rootfile_el.attrib['full-path']
            if opf_path not in names:
                return {'success': False, 'error': f'Package OPF ({opf_path}) non trovato all\'interno dell\'EPUB.'}
                
            opf = ET.fromstring(z.read(opf_path))
            title = opf.findtext('.//{*}title') or os.path.splitext(original_filename)[0]
            title = re.sub(r'<[^>]+>', '', title).strip()
            creator = opf.findtext('.//{*}creator') or 'Sconosciuto'
            lang = (opf.findtext('.//{*}language') or '').lower().strip()
            
            manifest = {item.attrib['id']: item.attrib for item in opf.findall('.//{*}manifest/{*}item')}
            spine_itemrefs = opf.findall('.//{*}spine/{*}itemref')
            if not spine_itemrefs:
                return {'success': False, 'error': 'L\'EPUB non contiene capitoli leggibili nello spine.'}
                
            opf_dir = os.path.dirname(opf_path)
            
            # --- Japanese Verification ---
            ja_char_count = 0
            has_ruby = False
            has_vrtl = False
            
            # Sample first 8 text chapters
            for itemref in spine_itemrefs[:8]:
                idref = itemref.attrib.get('idref')
                if idref in manifest:
                    href = manifest[idref]['href']
                    full_p = os.path.normpath(os.path.join(opf_dir, href)).replace('\\', '/')
                    for name in names:
                        if name == full_p or name.endswith(href):
                            if any(name.lower().endswith(ext) for ext in ['.xhtml', '.html', '.htm']):
                                html_content = z.read(name).decode('utf-8', errors='ignore')
                                if '<ruby' in html_content:
                                    has_ruby = True
                                if 'vrtl' in html_content or 'vertical-rl' in html_content:
                                    has_vrtl = True
                                clean_text = re.sub(r'<[^>]+>', '', html_content)
                                ja_chars = re.findall(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', clean_text)
                                ja_char_count += len(ja_chars)
                            break

            # Strong Japanese criteria:
            # - More than 30 Japanese characters in sample
            # - Or contains <ruby> furigana tags
            # - Or language tag starts with ja/jp and has Japanese text
            is_japanese = (ja_char_count >= 30) or has_ruby or ((lang.startswith('ja') or lang.startswith('jp')) and ja_char_count >= 10)
            
            warning_msg = None
            if not is_japanese:
                warning_msg = (
                    f"Il libro importato risulta in lingua non-giapponese (rilevata lingua: '{lang or 'en'}'). "
                    "È possibile leggerlo normalmente, ma le funzioni di segmentazione, dizionario e auto-furigana sono ottimizzate per testi in lingua giapponese."
                )

        # Safe save into BOOKS_DIR
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', original_filename).strip()
        if not safe_name.lower().endswith('.epub'):
            safe_name += '.epub'
            
        target_path = os.path.join(BOOKS_DIR, safe_name)
        
        # Avoid clobbering different file with same name
        counter = 1
        name_no_ext, ext = os.path.splitext(safe_name)
        while os.path.exists(target_path):
            if os.path.getsize(target_path) == len(file_bytes):
                break # Exact duplicate, overwrite safely
            target_path = os.path.join(BOOKS_DIR, f"{name_no_ext}_{counter}{ext}")
            counter += 1

        with open(target_path, 'wb') as f:
            f.write(file_bytes)
            
        # Rescan library immediately
        scan_books(force_reload=True)
        book_id = get_book_id(target_path)
        book_info = get_book(book_id)
        
        return {
            'success': True,
            'is_japanese': is_japanese,
            'message': f"Volume '{title}' importato con successo!",
            'warning': warning_msg,
            'book': book_info
        }
    except Exception as e:
        return {'success': False, 'error': f'Errore durante l\'importazione: {str(e)}'}

def get_table_of_contents(book_id):
    book = get_book(book_id)
    if not book:
        return []
        
    toc_entries = []
    try:
        with zipfile.ZipFile(book['filepath'], 'r') as z:
            opf = ET.fromstring(z.read(book['opf_path']))
            manifest = {item.attrib['id']: item.attrib for item in opf.findall('.//{*}manifest/{*}item')}
            opf_dir = book['opf_dir']
            
            # Spine href map to index
            spine_index_map = {}
            for idx, itemref in enumerate(opf.findall('.//{*}spine/{*}itemref')):
                idref = itemref.attrib.get('idref')
                if idref in manifest:
                    norm_href = os.path.normpath(os.path.join(opf_dir, manifest[idref]['href'])).replace('\\', '/')
                    spine_index_map[norm_href] = idx
                    spine_index_map[manifest[idref]['href']] = idx
            
            # 1. Try EPUB 3 Navigation Document
            nav_item = None
            for item in manifest.values():
                if 'nav' in item.get('properties', '').split():
                    nav_item = item
                    break
            
            if nav_item:
                nav_href = os.path.normpath(os.path.join(opf_dir, nav_item['href'])).replace('\\', '/')
                if nav_href in z.namelist():
                    soup = BeautifulSoup(z.read(nav_href), 'html.parser')
                    nav_toc = soup.find('nav', attrs={'epub:type': 'toc'}) or soup.find('nav')
                    if nav_toc:
                        for a in nav_toc.find_all('a'):
                            text = a.get_text(strip=True)
                            href = a.get('href', '')
                            clean_href = href.split('#')[0]
                            full_target = os.path.normpath(os.path.join(os.path.dirname(nav_href), clean_href)).replace('\\', '/')
                            spine_idx = spine_index_map.get(full_target, spine_index_map.get(clean_href, 0))
                            if text:
                                toc_entries.append({
                                    'title': text,
                                    'href': href,
                                    'spine_index': spine_idx
                                })

            # 2. Try EPUB 2 NCX if TOC is empty
            if not toc_entries:
                ncx_id = opf.find('.//{*}spine').attrib.get('toc')
                ncx_item = manifest.get(ncx_id) if ncx_id else None
                if not ncx_item:
                    for item in manifest.values():
                        if 'ncx' in item.get('media-type', '') or item['href'].endswith('.ncx'):
                            ncx_item = item
                            break
                            
                if ncx_item:
                    ncx_href = os.path.normpath(os.path.join(opf_dir, ncx_item['href'])).replace('\\', '/')
                    if ncx_href in z.namelist():
                        ncx_tree = ET.fromstring(z.read(ncx_href))
                        for navpoint in ncx_tree.findall('.//{*}navPoint'):
                            text = navpoint.findtext('.//{*}text') or ''
                            content_el = navpoint.find('.//{*}content')
                            src = content_el.attrib.get('src', '') if content_el is not None else ''
                            clean_src = src.split('#')[0]
                            full_target = os.path.normpath(os.path.join(opf_dir, clean_src)).replace('\\', '/')
                            spine_idx = spine_index_map.get(full_target, spine_index_map.get(clean_src, 0))
                            if text.strip():
                                toc_entries.append({
                                    'title': text.strip(),
                                    'href': src,
                                    'spine_index': spine_idx
                                })
                                
    except Exception as e:
        print(f"Error loading TOC for {book_id}: {e}")

    return toc_entries

def get_chapter_content(book_id, spine_index):
    book = get_book(book_id)
    if not book:
        return None
        
    try:
        with zipfile.ZipFile(book['filepath'], 'r') as z:
            opf = ET.fromstring(z.read(book['opf_path']))
            manifest = {item.attrib['id']: item.attrib for item in opf.findall('.//{*}manifest/{*}item')}
            spine_itemrefs = opf.findall('.//{*}spine/{*}itemref')
            
            if spine_index < 0 or spine_index >= len(spine_itemrefs):
                return None
                
            idref = spine_itemrefs[spine_index].attrib.get('idref')
            if idref not in manifest:
                return None
                
            chapter_item = manifest[idref]
            opf_dir = book['opf_dir']
            chapter_href = os.path.normpath(os.path.join(opf_dir, chapter_item['href'])).replace('\\', '/')
            chapter_dir = os.path.dirname(chapter_href)
            
            raw_content = z.read(chapter_href)
            soup = BeautifulSoup(raw_content, 'html.parser')
            
            # Rewrite image sources
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and not src.startswith(('http://', 'https://', 'data:')):
                    res_path = os.path.normpath(os.path.join(chapter_dir, src)).replace('\\', '/')
                    img['src'] = f"/api/book/{book_id}/resource?path={res_path}"
                    img['loading'] = 'lazy'
                    img['class'] = (img.get('class', []) if isinstance(img.get('class'), list) else [img.get('class', '')]) + ['reader-ill-img']

            # Rewrite SVG image elements
            for svg_img in soup.find_all('image'):
                href = svg_img.get('xlink:href') or svg_img.get('href')
                if href and not href.startswith(('http://', 'https://', 'data:')):
                    res_path = os.path.normpath(os.path.join(chapter_dir, href)).replace('\\', '/')
                    svg_img['xlink:href'] = f"/api/book/{book_id}/resource?path={res_path}"
                    svg_img['href'] = f"/api/book/{book_id}/resource?path={res_path}"
                    
            # Rewrite CSS link tags
            for link in soup.find_all('link', rel='stylesheet'):
                href = link.get('href')
                if href and not href.startswith(('http://', 'https://')):
                    res_path = os.path.normpath(os.path.join(chapter_dir, href)).replace('\\', '/')
                    link['href'] = f"/api/book/{book_id}/resource?path={res_path}"

            # Clean head: remove restrictive fixed viewports
            for meta in soup.find_all('meta', attrs={'name': 'viewport'}):
                meta.decompose()

            # Extract body content and detected is_vertical
            body = soup.find('body')
            html_tag = soup.find('html')
            
            classes = []
            if html_tag and html_tag.get('class'):
                classes.extend(html_tag.get('class') if isinstance(html_tag.get('class'), list) else [html_tag.get('class')])
            if body and body.get('class'):
                classes.extend(body.get('class') if isinstance(body.get('class'), list) else [body.get('class')])
                
            is_vertical = any('vrtl' in c for c in classes) or 'vrtl' in str(html_tag.get('class', ''))
            
            # Character count estimation
            plain_text = body.get_text() if body else ''
            # Count only non-whitespace Japanese/CJK/alphanumeric characters
            char_count = len(re.findall(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff\w]', plain_text))
            
            body_html = str(body) if body else str(soup)
            
            return {
                'book_id': book_id,
                'spine_index': spine_index,
                'total_spine': len(spine_itemrefs),
                'chapter_title': soup.title.string if soup.title else f"Parte {spine_index + 1}",
                'content_html': body_html,
                'is_vertical': is_vertical,
                'char_count': char_count,
                'prev_index': spine_index - 1 if spine_index > 0 else None,
                'next_index': spine_index + 1 if spine_index < len(spine_itemrefs) - 1 else None
            }
    except Exception as e:
        print(f"Error loading chapter {spine_index} for {book_id}: {e}")
        return None

def get_resource_data(book_id, resource_path):
    book = get_book(book_id)
    if not book:
        return None, None
        
    try:
        with zipfile.ZipFile(book['filepath'], 'r') as z:
            clean_path = os.path.normpath(resource_path).replace('\\', '/')
            if clean_path in z.namelist():
                data = z.read(clean_path)
                mime, _ = mimetypes.guess_type(clean_path)
                if not mime:
                    if clean_path.endswith('.css'):
                        mime = 'text/css'
                    elif clean_path.endswith(('.jpg', '.jpeg')):
                        mime = 'image/jpeg'
                    elif clean_path.endswith('.png'):
                        mime = 'image/png'
                    elif clean_path.endswith('.svg'):
                        mime = 'image/svg+xml'
                    elif clean_path.endswith('.xhtml'):
                        mime = 'application/xhtml+xml'
                    else:
                        mime = 'application/octet-stream'
                return data, mime
    except Exception as e:
        print(f"Error loading resource {resource_path} for {book_id}: {e}")
        
    return None, None
