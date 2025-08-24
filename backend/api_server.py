    # ...existing code...
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
import sys
import platform

from pymongo import MongoClient
from dotenv import load_dotenv

import pathlib
# Robust .env loading for EXE and dev
def robust_load_dotenv():
    # Try current working dir
    dotenv_paths = [
        pathlib.Path.cwd() / '.env',
        pathlib.Path(__file__).parent / '.env'
    ]
    # If running in PyInstaller bundle, also try _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        dotenv_paths.append(pathlib.Path(sys._MEIPASS) / '.env')
    for dotenv_path in dotenv_paths:
        if dotenv_path.exists():
            load_dotenv(dotenv_path)
            print(f"[DEBUG] Loaded .env from: {dotenv_path}")
            break
    else:
        print("[WARNING] .env file not found in any expected location!")

robust_load_dotenv()
from gpt_engine import GPTEngine
from resume_parser import extract_text_from_pdf

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def get_frontend_build_dir() -> str:
    """Resolve the path to the React build directory, compatible with PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        packaged_dir = os.path.join(sys._MEIPASS, 'frontend', 'build')
        if os.path.exists(packaged_dir):
            return packaged_dir
    return os.path.join(PROJECT_ROOT, 'frontend', 'build')

FRONTEND_BUILD_DIR = get_frontend_build_dir()
print(f"[DEBUG] Frontend build exists: {os.path.exists(FRONTEND_BUILD_DIR)}")

# --- MongoDB Atlas connection ---
# Replace with your actual MongoDB Atlas connection string
MONGO_URI = os.environ.get('MONGO_URI', 'YOUR_MONGODB_ATLAS_CONNECTION_STRING')
client = MongoClient(MONGO_URI)
db = client['ai_assistant']
users_col = db['users']

def get_user(email):
    return users_col.find_one({'email': email})

def create_user(email, password):
    if get_user(email):
        return False
    hashed = generate_password_hash(password)
    users_col.insert_one({'email': email, 'password': hashed, 'credits': 10})
    return True

def authenticate(email, password):
    user = get_user(email)
    if not user:
        return False
    return check_password_hash(user['password'], password)

def get_credits(email):
    user = get_user(email)
    if not user:
        return 0
    return user.get('credits', 0)

def use_credit(email):
    user = get_user(email)
    if not user or user.get('credits', 0) <= 0:
        return False
    users_col.update_one({'email': email}, {'$inc': {'credits': -1}})
    return True

app = Flask(__name__, static_folder=FRONTEND_BUILD_DIR, static_url_path='')

# OS-safe absolute upload directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR

# Allow requests from frontend
CORS(app)

# --- Auth & Credits Endpoints ---
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password required'}), 400
    if create_user(email, password):
        return jsonify({'success': True, 'message': 'User created'})
    else:
        return jsonify({'success': False, 'message': 'User already exists'}), 409
    
@app.route('/logout', methods=['POST'])
def logout():
    # For stateless JWT or sessionless, just return success. For session-based, clear session here.
    return jsonify({'success': True, 'message': 'Logged out'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if authenticate(email, password):
        return jsonify({'success': True, 'message': 'Login successful'})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/get_credits', methods=['POST'])
def get_credits_route():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if authenticate(email, password):
        credits = get_credits(email)
        return jsonify({'success': True, 'credits': credits})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/use_credit', methods=['POST'])
def use_credit_route():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if authenticate(email, password):
        if use_credit(email):
            credits = get_credits(email)
            return jsonify({'success': True, 'credits': credits})
        else:
            return jsonify({'success': False, 'message': 'No credits left'}), 403
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

gpt_engine = GPTEngine()

@app.route('/listen', methods=['POST'])
def listen():
    # Accept audio file (WAV) and transcribe with Whisper
    import tempfile
    import whisper
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file uploaded.'}), 400
    audio_file = request.files['audio']
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as tmp:
        audio_file.save(tmp.name)
        model = whisper.load_model('base')  # Use 'base' for speed, 'small' or 'medium' for accuracy
        result = model.transcribe(tmp.name, language='en')
        text = result.get('text', '').strip()
    return jsonify({'text': text})

@app.route('/transcribe', methods=['POST'])
def transcribe():
    # Alias for /listen endpoint for frontend compatibility
    return listen()

@app.get('/health')
def health():
    return jsonify({
        'status': 'ok',
        'os': platform.system(),
        'release': platform.release(),
        'platform': platform.platform()
    })


@app.route('/ask', methods=['POST'])
def ask():
    # Log the OS type for each request (cross-platform support)
    print(f"[DEBUG] Backend running on OS: {platform.system()} {platform.release()} ({platform.platform()})")
    # Block if user has no credits
    email = None
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        email = request.form.get('email', None)
    else:
        data = request.get_json(silent=True)
        if data:
            email = data.get('email', None)
    if email:
        user = get_user(email)
        if not user or user.get('credits', 0) <= 0:
            return jsonify({'answer': 'No credits left. Please purchase more credits to continue.'}), 403
    # If multipart/form-data, handle file upload
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        question = request.form.get('question', '')
        mode = request.form.get('mode', 'global')
        history = request.form.get('history', None)
        resume_file = request.files.get('resume')
        resume_text = None
        if resume_file:
            filename = secure_filename(resume_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            resume_file.save(file_path)
            # Always use the same logic as desktop: parse PDF or text
            if filename.lower().endswith('.pdf'):
                resume_text = extract_text_from_pdf(file_path)
            else:
                # Try to parse as text, fallback to empty string if error
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        resume_text = f.read()
                except Exception:
                    resume_text = ''
            # Debug print: show filename and first 200 chars of resume text
            print(f"[DEBUG] Resume file received: {filename}")
            print(f"[DEBUG] Resume text length: {len(resume_text) if resume_text else 0}")
            print("[DEBUG] Resume text preview (first 200 chars):\n", (resume_text or '')[:200])
            if not resume_text or not resume_text.strip():
                print(f"[WARNING] Resume text is empty after extraction for file: {filename}")
        else:
            resume_text = None
        # Parse history if present
        import json as _json
        if history:
            try:
                history = _json.loads(history)
            except Exception:
                history = []
        else:
            history = []
        if not question:
            return jsonify({'answer': 'No question provided.'}), 400
        
        # CRITICAL FIX: If Smart mode is requested, ALWAYS use resume mode regardless of resume_text
        if mode == 'resume':
            print(f"[DEBUG] Smart mode requested - using resume context (resume_text_len={len(resume_text) if resume_text else 0})")
            if not resume_text or not resume_text.strip():
                return jsonify({
                    'answer': 'Could not extract any text from the uploaded resume. If your PDF is a scanned image, try a text-based PDF or upload a .txt file instead.',
                    'resume_text': ''
                }), 422
            answer = gpt_engine.generate_response(question, resume_text=resume_text, mode="resume", history=history)
            return jsonify({'answer': answer, 'resume_text': resume_text})
        else:
            # Global mode
            answer = gpt_engine.generate_response(question, resume_text=resume_text, mode="global", history=history)
            return jsonify({'answer': answer})
    # Else, handle JSON (old flow)
    data = request.get_json()
    question = data.get('question', '')
    resume = data.get('resume', None)
    mode = data.get('mode', 'global')
    history = data.get('history', [])
    if not question:
        return jsonify({'answer': 'No question provided.'}), 400
    answer = gpt_engine.generate_response(question, resume_text=resume, mode=mode, history=history)
    return jsonify({'answer': answer})


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path: str):
    if path == '':
        return send_from_directory(FRONTEND_BUILD_DIR, 'index.html')
    return app.send_static_file(path)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False)
