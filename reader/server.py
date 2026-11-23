import os
import sys
import io
import csv
import json
import socket
import qrcode
from flask import Flask, request, jsonify, send_file, render_template, Response

import database
import epub_parser
import dictionary_manager
import furigana_manager
import translator_manager

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

app = Flask(__name__, static_folder='static', template_folder='templates')

# Init on module load (needed for gunicorn --preload)
database.init_db()
epub_parser.scan_books()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def web_manifest():
    manifest_data = {
        "name": "Re:Zero Japanese Reader",
        "short_name": "Re:Zero",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#12141a",
        "theme_color": "#8b5cf6",
        "description": "Japanese Light Novel Reader for Re:Zero"
    }
    return jsonify(manifest_data)

@app.route('/api/server_info')
def server_info():
    fly_app = os.environ.get('FLY_APP_NAME')
    if fly_app:
        public_url = f"https://{fly_app}.fly.dev"
        return jsonify({
            'lan_ip': fly_app + '.fly.dev',
            'port': 443,
            'url': public_url,
            'local_url': public_url
        })
    ip = get_lan_ip()
    port = int(os.environ.get('PORT', 5173))
    return jsonify({
        'lan_ip': ip,
        'port': port,
        'url': f"http://{ip}:{port}",
        'local_url': f"http://localhost:{port}"
    })

@app.route('/api/qr')
def get_qr_code():
    # On Fly.io use FLY_APP_NAME env var; fallback to LAN
    fly_app = os.environ.get('FLY_APP_NAME')
    if fly_app:
        url = f"https://{fly_app}.fly.dev"
    else:
        ip = get_lan_ip()
        port = int(os.environ.get('PORT', 5173))
        url = f"http://{ip}:{port}"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')

# --- Books & EPUB APIs ---

@app.route('/api/books/upload', methods=['POST'])
def upload_epub():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Nessun file inviato.'}), 400
        
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Nome file non valido.'}), 400
        
    if not file.filename.lower().endswith('.epub'):
        return jsonify({'success': False, 'error': 'Il file deve avere estensione .epub.'}), 400
        
    content = file.read()
    res = epub_parser.validate_and_import_epub(content, file.filename)
    if res.get('success'):
        return jsonify(res), 200
    else:
        return jsonify(res), 400

@app.route('/api/books/rescan', methods=['POST'])
def rescan_books():
    books = epub_parser.scan_books(force_reload=True)
    return jsonify({'status': 'ok', 'count': len(books)})

@app.route('/api/books')
def get_books():
    books = epub_parser.scan_books()
    all_progress = database.get_all_progress()
    
    result = []
    for b in books:
        prog = all_progress.get(b['id'], {})
        b_data = dict(b)
        b_data['cover_url'] = f"/api/book/{b['id']}/cover"
        b_data['progress'] = {
            'spine_index': prog.get('spine_index', 0),
            'scroll_ratio': prog.get('scroll_ratio', 0.0),
            'chapter_title': prog.get('chapter_title', ''),
            'updated_at': prog.get('updated_at', ''),
            'percent': round((prog.get('spine_index', 0) / max(b['total_spine'], 1)) * 100, 1),
            'total_seconds': prog.get('total_seconds', 0),
            'total_chars': prog.get('total_chars', 0)
        }
        result.append(b_data)
        
    return jsonify(result)

@app.route('/api/book/<book_id>')
def get_book_details(book_id):
    book = epub_parser.get_book(book_id)
    if not book:
        return jsonify({'error': 'Book not found'}), 404
        
    prog = database.get_progress(book_id) or {}
    b_data = dict(book)
    b_data['cover_url'] = f"/api/book/{book['id']}/cover"
    b_data['progress'] = prog
    return jsonify(b_data)

@app.route('/api/book/<book_id>/cover')
def get_book_cover(book_id):
    book = epub_parser.get_book(book_id)
    if not book or not book.get('cover_path'):
        # Fallback to 1x1 transparent or placeholder
        return Response(status=404)
        
    data, mime = epub_parser.get_resource_data(book_id, book['cover_path'])
    if data:
        return Response(data, mimetype=mime, headers={'Cache-Control': 'public, max-age=86400'})
    return Response(status=404)

@app.route('/api/book/<book_id>/toc')
def get_toc(book_id):
    toc = epub_parser.get_table_of_contents(book_id)
    return jsonify(toc)

@app.route('/api/book/<book_id>/chapter/<int:spine_index>')
def get_chapter(book_id, spine_index):
    furigana_mode = request.args.get('furigana', 'original')
    chapter = epub_parser.get_chapter_content(book_id, spine_index)
    if not chapter:
        return jsonify({'error': 'Chapter not found'}), 404

    # If auto furigana requested, inject furigana into kanji lacking ruby
    if furigana_mode == 'auto':
        try:
            chapter['content_html'] = furigana_manager.inject_furigana_into_html(chapter['content_html'])
        except Exception as e:
            print(f"Auto-furigana injection error: {e}")

    return jsonify(chapter)

@app.route('/api/book/<book_id>/resource')
def get_resource(book_id):
    res_path = request.args.get('path')
    if not res_path:
        return Response(status=400)
        
    data, mime = epub_parser.get_resource_data(book_id, res_path)
    if data:
        # If it's CSS, inject user-friendly override rules if needed
        return Response(data, mimetype=mime, headers={'Cache-Control': 'public, max-age=86400'})
    return Response(status=404)

# --- Dictionary & Furigana APIs ---

@app.route('/api/dictionary/lookup')
def lookup_word():
    word = request.args.get('word', '').strip()
    if not word:
        return jsonify({'found': False, 'results': []})
        
    result = dictionary_manager.full_lookup(word)
    return jsonify(result)

@app.route('/api/dictionary/jisho')
def lookup_jisho():
    word = request.args.get('word', '').strip()
    if not word:
        return jsonify([])
    items = dictionary_manager.query_jisho(word)
    return jsonify(items)

@app.route('/api/furigana', methods=['POST'])
def make_furigana():
    data = request.json or {}
    text = data.get('text', '')
    html_with_ruby = furigana_manager.add_furigana_to_text(text)
    tokens = furigana_manager.analyze_tokens(text)
    return jsonify({
        'ruby_html': html_with_ruby,
        'tokens': tokens
    })

# --- Translation API ---

@app.route('/api/translate', methods=['POST'])
def translate_api():
    data = request.json or {}
    text = data.get('text', '').strip()
    target_lang = data.get('lang', 'it')
    res = translator_manager.translate_text(text, target_lang=target_lang)
    return jsonify(res)

# --- Reading Progress & Stats ---

@app.route('/api/progress/<book_id>')
def get_book_progress(book_id):
    prog = database.get_progress(book_id)
    return jsonify(prog or {})

@app.route('/api/progress', methods=['POST'])
def update_progress():
    data = request.json or {}
    book_id = data.get('book_id')
    spine_index = data.get('spine_index', 0)
    scroll_ratio = data.get('scroll_ratio', 0.0)
    chapter_title = data.get('chapter_title', '')
    seconds = data.get('seconds', 0)
    chars = data.get('chars', 0)
    
    if book_id:
        database.save_progress(book_id, spine_index, scroll_ratio, chapter_title, seconds, chars)
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'Missing book_id'}), 400

@app.route('/api/stats')
def get_stats():
    stats = database.get_overall_stats()
    return jsonify(stats)

# --- Bookmarks ---

@app.route('/api/bookmarks')
def list_bookmarks():
    book_id = request.args.get('book_id')
    bookmarks = database.get_bookmarks(book_id)
    return jsonify(bookmarks)

@app.route('/api/bookmarks', methods=['POST'])
def create_bookmark():
    data = request.json or {}
    b_id = database.add_bookmark(
        data.get('book_id'),
        data.get('spine_index', 0),
        data.get('chapter_title', ''),
        data.get('snippet', ''),
        data.get('note', '')
    )
    return jsonify({'status': 'ok', 'id': b_id})

@app.route('/api/bookmarks/<int:bookmark_id>', methods=['DELETE'])
def remove_bookmark(bookmark_id):
    database.delete_bookmark(bookmark_id)
    return jsonify({'status': 'ok'})

# --- Mined Vocab (Words) ---

@app.route('/api/vocab')
def list_vocab():
    words = database.get_mined_words()
    return jsonify(words)

@app.route('/api/vocab', methods=['POST'])
def create_vocab():
    data = request.json or {}
    word_id = database.add_mined_word(
        data.get('word', ''),
        data.get('reading', ''),
        data.get('definition', ''),
        data.get('sentence', ''),
        data.get('source_book', ''),
        data.get('status', 'learning')
    )
    return jsonify({'status': 'ok', 'id': word_id})

@app.route('/api/vocab/<int:word_id>', methods=['DELETE'])
def remove_vocab(word_id):
    database.delete_mined_word(word_id)
    return jsonify({'status': 'ok'})

@app.route('/api/vocab/<int:word_id>/status', methods=['PUT'])
def update_vocab_status(word_id):
    data = request.json or {}
    status = data.get('status', 'learning')
    database.update_mined_word_status(word_id, status)
    return jsonify({'status': 'ok'})

# --- Saved Sentences ---

@app.route('/api/sentences')
def list_sentences():
    sentences = database.get_saved_sentences()
    return jsonify(sentences)

@app.route('/api/sentences', methods=['POST'])
def create_sentence():
    data = request.json or {}
    sent_id = database.add_saved_sentence(
        data.get('sentence', ''),
        data.get('translation', ''),
        data.get('note', ''),
        data.get('source_book', '')
    )
    return jsonify({'status': 'ok', 'id': sent_id})

@app.route('/api/sentences/<int:sent_id>', methods=['DELETE'])
def remove_sentence(sent_id):
    database.delete_saved_sentence(sent_id)
    return jsonify({'status': 'ok'})

# --- Seen Terms Tracking ---

@app.route('/api/seen_terms')
def get_seen_terms():
    terms = database.get_all_seen_terms()
    return jsonify(terms)

@app.route('/api/seen_terms', methods=['POST'])
def track_seen_term():
    data = request.json or {}
    term = data.get('term', '')
    status = data.get('status', 'learning')
    if term:
        database.set_term_status(term, status)
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'Missing term'}), 400

# --- Settings ---

@app.route('/api/settings')
def get_user_settings():
    settings = database.get_settings()
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
def save_user_setting():
    data = request.json or {}
    key = data.get('key')
    value = data.get('value')
    if key:
        database.set_setting(key, value)
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'Missing key'}), 400

# --- Anki & JSON Export ---

@app.route('/api/export/anki')
def export_anki():
    """
    Exports mined words as a TSV file formatted for direct Anki import:
    Word \t Reading \t Definition \t Sentence \t Source
    """
    words = database.get_mined_words()
    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t')
    writer.writerow(['# Word', 'Reading', 'Definition', 'Context Sentence', 'Source Book', 'Status'])
    for w in words:
        writer.writerow([
            w['word'],
            w['reading'],
            w['definition'],
            w['sentence'],
            w['source_book'],
            w['status']
        ])
    
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    return send_file(
        mem,
        mimetype='text/tab-separated-values',
        as_attachment=True,
        download_name='rezero_vocab_anki.tsv'
    )

@app.route('/api/export/json')
def export_json():
    data = {
        'vocab': database.get_mined_words(),
        'sentences': database.get_saved_sentences(),
        'bookmarks': database.get_bookmarks(),
        'stats': database.get_overall_stats(),
        'progress': database.get_all_progress()
    }
    mem = io.BytesIO()
    mem.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    mem.seek(0)
    return send_file(
        mem,
        mimetype='application/json',
        as_attachment=True,
        download_name='rezero_reader_backup.json'
    )

if __name__ == '__main__':
    port = 5173
    print(f"==================================================")
    print(f" Re:Zero Japanese Light Novel Reader")
    print(f" Server starting on http://localhost:{port}")
    print(f"==================================================")
    database.init_db()
    epub_parser.scan_books()
    app.run(host='0.0.0.0', port=port, debug=False)
