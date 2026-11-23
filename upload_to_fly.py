#!/usr/bin/env python3
"""
upload_to_fly.py — Carica EPUBs e EDICT su Fly.io volume via SSH/SCP
Esegui DOPO aver fatto: fly deploy

Richiede: flyctl installato e autenticato (fly auth login)
"""
import subprocess
import sys
import os
import glob

APP_NAME = "rezero-reader"
EPUB_DIR = os.path.dirname(os.path.abspath(__file__))
EDICT_PATH = os.path.join(EPUB_DIR, "reader_data", "edict.db")

def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if check and result.returncode != 0:
        print(f"ERRORE: comando fallito con codice {result.returncode}")
        sys.exit(1)
    return result

def main():
    epubs = sorted(glob.glob(os.path.join(EPUB_DIR, "*.epub")))
    print(f"Trovati {len(epubs)} EPUB da uploadare")
    print(f"EDICT: {os.path.exists(EDICT_PATH)}")
    print()

    # Crea directory sul volume tramite fly ssh console
    print("=== Creazione directory /data/epubs e /data/reader_data ===")
    run(["fly", "ssh", "console", "-a", APP_NAME, "-C",
         "mkdir -p /data/epubs /data/reader_data"])

    # Upload EPUBs
    print(f"\n=== Upload {len(epubs)} EPUBs → /data/epubs/ ===")
    for i, epub_path in enumerate(epubs, 1):
        fname = os.path.basename(epub_path)
        print(f"[{i}/{len(epubs)}] {fname}")
        run(["fly", "sftp", "shell", "-a", APP_NAME],
            check=False)  # Interactive - usare il batch mode sotto

    # Usa fly ssh sftp in batch
    print("\n=== Upload EPUBs via fly sftp ===")
    for i, epub_path in enumerate(epubs, 1):
        fname = os.path.basename(epub_path)
        print(f"[{i}/{len(epubs)}] {fname} ({os.path.getsize(epub_path)//1024//1024} MB)")
        result = subprocess.run(
            ["fly", "sftp", "get", "-a", APP_NAME,
             f"/data/epubs/{fname}"],  # Questo e' un get test
            capture_output=True
        )
        # Fly non ha sftp put direttamente - usare il workaround seguente

    print("""
==========================================================
NOTA: fly sftp non supporta upload diretto di file binari.
Usa il metodo alternativo con fly proxy + scp:

1. In un terminale separato, avvia il proxy:
   fly proxy 2222:22 -a rezero-reader

2. In un altro terminale, copia i file:
   scp -P 2222 -o StrictHostKeyChecking=no *.epub root@localhost:/data/epubs/
   scp -P 2222 -o StrictHostKeyChecking=no reader_data/edict.db root@localhost:/data/reader_data/

Oppure usa lo script PowerShell: deploy_files.ps1
==========================================================
""")

if __name__ == '__main__':
    main()
