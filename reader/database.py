import sqlite3
import os
import json
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reader_data', 'user_data.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Reading progress per book
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reading_progress (
                book_id TEXT PRIMARY KEY,
                spine_index INTEGER DEFAULT 0,
                scroll_ratio REAL DEFAULT 0.0,
                chapter_title TEXT DEFAULT '',
                updated_at TEXT,
                total_seconds INTEGER DEFAULT 0,
                total_chars INTEGER DEFAULT 0,
                is_finished INTEGER DEFAULT 0
            )
        ''')

        # Reading sessions / daily history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reading_history (
                day TEXT PRIMARY KEY,
                characters_read INTEGER DEFAULT 0,
                seconds_read INTEGER DEFAULT 0
            )
        ''')

        # Bookmarks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id TEXT,
                spine_index INTEGER,
                chapter_title TEXT,
                snippet TEXT,
                note TEXT DEFAULT '',
                created_at TEXT
            )
        ''')

        # Mined words / Vocab
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mined_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT,
                reading TEXT,
                definition TEXT,
                sentence TEXT,
                source_book TEXT,
                status TEXT DEFAULT 'learning', -- 'learning' or 'known'
                created_at TEXT
            )
        ''')

        # Saved sentences
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sentence TEXT,
                translation TEXT,
                note TEXT,
                source_book TEXT,
                created_at TEXT
            )
        ''')

        # Seen / Tracked terms
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seen_terms (
                term TEXT PRIMARY KEY,
                reading TEXT,
                count INTEGER DEFAULT 1,
                status TEXT DEFAULT 'learning', -- 'learning' or 'known'
                first_seen TEXT,
                last_seen TEXT
            )
        ''')

        # Settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Translation cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translation_cache (
                source_text TEXT PRIMARY KEY,
                translated_text TEXT,
                target_lang TEXT,
                created_at TEXT
            )
        ''')
        
        conn.commit()

# --- Progress & Stats ---

def get_progress(book_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM reading_progress WHERE book_id = ?', (book_id,)).fetchone()
        if row:
            return dict(row)
        return None

def save_progress(book_id, spine_index, scroll_ratio, chapter_title="", added_seconds=0, added_chars=0):
    now = datetime.now().isoformat()
    today = date.today().isoformat()
    with get_db() as conn:
        # Update progress
        conn.execute('''
            INSERT INTO reading_progress (book_id, spine_index, scroll_ratio, chapter_title, updated_at, total_seconds, total_chars)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                spine_index = excluded.spine_index,
                scroll_ratio = excluded.scroll_ratio,
                chapter_title = CASE WHEN excluded.chapter_title != '' THEN excluded.chapter_title ELSE chapter_title END,
                updated_at = excluded.updated_at,
                total_seconds = total_seconds + excluded.total_seconds,
                total_chars = total_chars + excluded.total_chars
        ''', (book_id, spine_index, scroll_ratio, chapter_title, now, added_seconds, added_chars))

        # Update daily history
        if added_chars > 0 or added_seconds > 0:
            conn.execute('''
                INSERT INTO reading_history (day, characters_read, seconds_read)
                VALUES (?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    characters_read = characters_read + excluded.characters_read,
                    seconds_read = seconds_read + excluded.seconds_read
            ''', (today, added_chars, added_seconds))

        conn.commit()

def get_all_progress():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM reading_progress').fetchall()
        return {r['book_id']: dict(r) for r in rows}

def get_overall_stats():
    today = date.today().isoformat()
    with get_db() as conn:
        total_time = conn.execute('SELECT SUM(seconds_read) as s, SUM(characters_read) as c FROM reading_history').fetchone()
        today_stat = conn.execute('SELECT seconds_read, characters_read FROM reading_history WHERE day = ?', (today,)).fetchone()
        history_rows = conn.execute('SELECT day, characters_read, seconds_read FROM reading_history ORDER BY day DESC LIMIT 30').fetchall()
        total_words = conn.execute('SELECT COUNT(*) as cnt FROM mined_words').fetchone()['cnt']
        known_words = conn.execute("SELECT COUNT(*) as cnt FROM seen_terms WHERE status = 'known'").fetchone()['cnt']
        learning_words = conn.execute("SELECT COUNT(*) as cnt FROM seen_terms WHERE status = 'learning'").fetchone()['cnt']

        return {
            'total_seconds': total_time['s'] or 0,
            'total_characters': total_time['c'] or 0,
            'today_seconds': today_stat['seconds_read'] if today_stat else 0,
            'today_characters': today_stat['characters_read'] if today_stat else 0,
            'total_mined_words': total_words,
            'known_words': known_words,
            'learning_words': learning_words,
            'history': [dict(r) for r in history_rows]
        }

# --- Bookmarks ---

def add_bookmark(book_id, spine_index, chapter_title, snippet, note=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO bookmarks (book_id, spine_index, chapter_title, snippet, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (book_id, spine_index, chapter_title, snippet, note, now))
        conn.commit()
        return cursor.lastrowid

def get_bookmarks(book_id=None):
    with get_db() as conn:
        if book_id:
            rows = conn.execute('SELECT * FROM bookmarks WHERE book_id = ? ORDER BY id DESC', (book_id,)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM bookmarks ORDER BY id DESC').fetchall()
        return [dict(r) for r in rows]

def delete_bookmark(bookmark_id):
    with get_db() as conn:
        conn.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))
        conn.commit()

# --- Mined Words (Vocab) ---

def add_mined_word(word, reading, definition, sentence, source_book, status='learning'):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO mined_words (word, reading, definition, sentence, source_book, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (word, reading, definition, sentence, source_book, status, now))
        conn.commit()
        last_id = cursor.lastrowid
        
    track_term_seen(word, reading=reading, status=status)
    return last_id

def get_mined_words():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM mined_words ORDER BY id DESC').fetchall()
        return [dict(r) for r in rows]

def delete_mined_word(word_id):
    with get_db() as conn:
        conn.execute('DELETE FROM mined_words WHERE id = ?', (word_id,))
        conn.commit()

def update_mined_word_status(word_id, status):
    with get_db() as conn:
        row = conn.execute('SELECT word FROM mined_words WHERE id = ?', (word_id,)).fetchone()
        if row:
            word = row['word']
            conn.execute('UPDATE mined_words SET status = ? WHERE id = ?', (status, word_id))
            conn.execute('UPDATE seen_terms SET status = ? WHERE term = ?', (status, word))
            conn.commit()

# --- Saved Sentences ---

def add_saved_sentence(sentence, translation, note, source_book):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO saved_sentences (sentence, translation, note, source_book, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (sentence, translation, note, source_book, now))
        conn.commit()
        return cursor.lastrowid

def get_saved_sentences():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM saved_sentences ORDER BY id DESC').fetchall()
        return [dict(r) for r in rows]

def delete_saved_sentence(sentence_id):
    with get_db() as conn:
        conn.execute('DELETE FROM saved_sentences WHERE id = ?', (sentence_id,))
        conn.commit()

# --- Tracked Terms ---

def track_term_seen(term, reading="", status='learning'):
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute('''
            INSERT INTO seen_terms (term, reading, count, status, first_seen, last_seen)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                count = count + 1,
                last_seen = excluded.last_seen,
                status = CASE WHEN excluded.status != '' THEN excluded.status ELSE status END,
                reading = CASE WHEN excluded.reading != '' THEN excluded.reading ELSE reading END
        ''', (term, reading, status, now, now))
        conn.commit()

def get_all_seen_terms():
    with get_db() as conn:
        rows = conn.execute('SELECT term, reading, count, status FROM seen_terms').fetchall()
        return {r['term']: dict(r) for r in rows}

def set_term_status(term, status):
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute('''
            INSERT INTO seen_terms (term, count, status, first_seen, last_seen)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                status = excluded.status,
                last_seen = excluded.last_seen
        ''', (term, status, now, now))
        conn.commit()

# --- Settings ---

def get_settings():
    with get_db() as conn:
        rows = conn.execute('SELECT key, value FROM settings').fetchall()
        return {r['key']: json.loads(r['value']) if r['value'].startswith('{') or r['value'].startswith('[') else r['value'] for r in rows}

def set_setting(key, value):
    val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    with get_db() as conn:
        conn.execute('''
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''', (key, val_str))
        conn.commit()

# --- Translation Cache ---

def get_cached_translation(text, target_lang='it'):
    with get_db() as conn:
        row = conn.execute('SELECT translated_text FROM translation_cache WHERE source_text = ? AND target_lang = ?', (text, target_lang)).fetchone()
        return row['translated_text'] if row else None

def set_cached_translation(text, translated_text, target_lang='it'):
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute('''
            INSERT INTO translation_cache (source_text, translated_text, target_lang, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_text) DO UPDATE SET translated_text = excluded.translated_text
        ''', (text, translated_text, target_lang, now))
        conn.commit()

init_db()
