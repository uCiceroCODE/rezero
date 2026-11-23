#!/bin/bash
set -e

# Volume montato su /data — contiene EPUBs e databases
DATA_DIR="/data"
EPUB_DIR="$DATA_DIR/epubs"
READER_DATA="$DATA_DIR/reader_data"

# Crea struttura se non esiste
mkdir -p "$EPUB_DIR" "$READER_DATA"

# Link simbolici: il codice li cerca in /app/reader_data e nella cartella padre degli epub
# epub_parser.py calcola BOOKS_DIR come dirname(dirname(abspath(__file__)))
# = dirname(/app/reader/) = /app — quindi cercher? /app/*.epub
# Li linkhiamo da /data/epubs/*.epub a /app/*.epub via link soft
if [ -d "$EPUB_DIR" ] && [ "$(ls -A $EPUB_DIR/*.epub 2>/dev/null)" ]; then
    for f in "$EPUB_DIR"/*.epub; do
        fname=$(basename "$f")
        target="/app/$fname"
        if [ ! -L "$target" ]; then
            ln -s "$f" "$target"
        fi
    done
fi

# Link reader_data -> /data/reader_data (per DB persistenti)
if [ ! -L /app/reader_data ]; then
    if [ -d /app/reader_data ]; then
        # Copia eventuali file esistenti nel volume
        cp -rn /app/reader_data/. "$READER_DATA/" 2>/dev/null || true
        rm -rf /app/reader_data
    fi
    ln -s "$READER_DATA" /app/reader_data
fi

echo "=== Re:Zero Reader ==="
echo "EPUBs in $EPUB_DIR: $(ls $EPUB_DIR/*.epub 2>/dev/null | wc -l)"
echo "Starting gunicorn on port 8080..."

cd /app/reader
exec gunicorn \
    --bind 0.0.0.0:8080 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --preload \
    "server:app"
