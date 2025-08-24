
# --- NEW: Add Python-based speech recognition ---

import threading
import time
import webview
import os
import sys
import requests

# PyWebView 4.x+ API exposure (works for both sync and async JS calls)
import inspect
def expose_quit_api():
    def quit():
        import os
        import sys
        try:
            webview.windows[0].destroy()
        except Exception:
            pass
        os._exit(0)
    # Expose to JS
    if hasattr(webview, 'expose'):
        webview.expose(quit)
        return quit
    else:
        class Api:
            def quit(self):
                quit()
        return Api()

from api_server import app

def run_flask():
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    app.run(host=host, port=port, debug=False, use_reloader=False)

def run_speech_recognition():
    try:
        import speech_recognition as sr
    except ImportError:
        print('speech_recognition not installed. Voice input disabled.')
        return
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    print('Voice listening started. Speak into your microphone...')
    while True:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source)
        try:
            text = recognizer.recognize_google(audio)
            print(f'[VOICE] Recognized: {text}')
            # Send recognized text to backend /listen endpoint
            try:
                requests.post('http://127.0.0.1:5000/listen', json={'text': text})
            except Exception as e:
                print(f'[VOICE] Failed to send to backend: {e}')
        except sr.UnknownValueError:
            print('[VOICE] Could not understand audio')
        except sr.RequestError as e:
            print(f'[VOICE] Recognition error: {e}')

def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start speech recognition in a separate thread
    speech_thread = threading.Thread(target=run_speech_recognition, daemon=True)
    speech_thread.start()

    # Wait for server to be up
    time.sleep(1.5)
    url = 'http://127.0.0.1:5000/'

    # Create truly stealth window - transparent, frameless, undetectable
    window = webview.create_window(
        'System Monitor',  # Stealth title
        url, 
        width=900, 
        height=600, 
        resizable=True,
        on_top=True,
        frameless=True,
        transparent=True,
        easy_drag=True,
        min_size=(400, 300),
        # Stealth features
        text_select=False,
        confirm_close=False,
        # Position it subtly
        x=100,
        y=100
    )
    # Expose the quit API to JS (compatible with PyWebView 3.x and 4.x)
    api = expose_quit_api()
    webview.start(api, debug=False)

if __name__ == '__main__':
    # Ensure requests is imported so PyInstaller bundles it
    import requests
    main()