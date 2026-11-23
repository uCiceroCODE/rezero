import os
import sys
import webbrowser
import threading
import time
import socket
import qrcode

# Reconfigure stdout for UTF-8 so Japanese characters and QR blocks print cleanly
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add reader folder to path
reader_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reader')
sys.path.insert(0, reader_dir)

import server

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

def open_browser():
    time.sleep(1.2)
    url = "http://localhost:5173"
    print(f"Apertura del browser su PC: {url}...")
    webbrowser.open(url)

if __name__ == '__main__':
    threading.Thread(target=open_browser, daemon=True).start()
    port = 5173
    lan_ip = get_lan_ip()
    ipad_url = f"http://{lan_ip}:{port}"

    print(f"============================================================")
    print(f" ゼロ読 - Re:Zero Japanese Light Novel Reader")
    print(f"============================================================")
    print(f" • PC Locale:     http://localhost:{port}")
    print(f" • iPad / Rete:   {ipad_url}")
    print(f"============================================================")
    print(f" ACCESSO DA IPAD / TABLET (Stessa Rete Wi-Fi):")
    print(f" Inquadra questo codice QR con la fotocamera dell'iPad:")
    print(f"")
    try:
        qr = qrcode.QRCode()
        qr.add_data(ipad_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception as e:
        print(f" (QR visualizzabile anche nell'app su: {ipad_url})")
    print(f"")
    print(f" Suggerimento iPad: In Safari tocca 'Condividi' -> 'Aggiungi alla schermata Home'")
    print(f" per usarlo come app a schermo intero!")
    print(f" Premi CTRL+C per arrestare il server.")
    print(f"============================================================")

    server.database.init_db()
    server.epub_parser.scan_books()
    # Bind to 0.0.0.0 so iPad and other devices on LAN can connect
    server.app.run(host='0.0.0.0', port=port, debug=False)
