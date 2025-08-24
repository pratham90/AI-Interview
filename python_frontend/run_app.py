import threading
import webview
import app  # This imports your Flask app from app.py

def start_flask():
    app.app.run()

if __name__ == '__main__':
    threading.Thread(target=start_flask, daemon=True).start()
    webview.create_window('Live insights', 'http://127.0.0.1:5000')
