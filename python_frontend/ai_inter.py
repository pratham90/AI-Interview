import sys
import os
import json
import time
import threading
import queue
import tempfile
import wave
import requests
import numpy as np
import re # Added for regex in _format_answer_for_interview
import platform
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QAction, QShortcut, QKeySequence, QTextOption
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QFileDialog, QStackedWidget, QFrame, QMessageBox, QSizePolicy, QSpacerItem,
    QSlider
)
from concurrent.futures import ThreadPoolExecutor

BACKEND_URL = "http://127.0.0.1:5000"

HAVE_SPEECH_RECOGNITION = True
try:
    import speech_recognition as sr
except Exception:
    HAVE_SPEECH_RECOGNITION = False

# Background executor to keep UI and listener responsive
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="AI_BG")

def glass(bg="rgba(0,0,0,0.5)"):
    return f"""
        background-color: {bg};
        border-radius: 18px;
        color: #fff;
    """

def glass_panel(bg="rgba(35,35,35,0.85)"):
    return f"""
        background-color: {bg};
        border: 1px solid #333;
        border-radius: 14px;
    """

def header_style():
    return """
        background-color: rgba(24,24,24,0.95);
        border-bottom: 1px solid #444;
        border-radius: 18px 18px 0 0;
        color: #fff;
        font-weight: 600;
        font-size: 16px;
        cursor: grab;
    """

def textedit_style():
    return """
        QTextEdit {
            background: rgba(40,40,40,0.95);
            border: none;
            border-radius: 10px;
            color: #fff;
            padding: 12px;
            line-height: 1.6;
            font-size: 14px;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        QScrollBar:vertical {
            background: rgba(255,255,255,0.1);
            width: 10px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.3);
            border-radius: 6px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(255,255,255,0.5);
        }
    """

def button_primary():
    return """
        QPushButton {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2563eb, stop:1 #42a5f5);
            color: white;
            font-weight: 700;
            border: none;
            border-radius: 24px;
            padding: 10px 16px;
        }
        QPushButton:hover {
            background: #3b82f6;
        }
        QPushButton:disabled {
            background: #2b2b2b;
            color: #888;
        }
    """

def button_danger_round():
    return """
        QPushButton {
            background: rgba(239,68,68,0.9);
            color: white;
            border: none;
            border-radius: 13px;
            width: 26px;
            height: 26px;
            font-size: 14px;
        }
        QPushButton:hover {
            background: rgba(239,68,68,1);
        }
    """

def input_style():
    return """
        QLineEdit {
            padding: 8px;
            color: #fff;
            background: rgba(24,24,24,0.95);
            border: 1px solid #333;
            border-radius: 6px;
            font-size: 14px;
        }
    """

class SpeechRecognitionThread(QThread):
    recognized = Signal(str)
    error = Signal(str)
    listening_status = Signal(str)

    def __init__(self, language="en-US", parent=None):
        super().__init__(parent)
        self.language = language
        self.running = False
        self.recognizer = None
        self.microphone = None
        
        # Platform-specific optimizations
        self.platform = platform.system().lower()
        self.is_windows = self.platform == "windows"
        self.is_macos = self.platform == "darwin"
        self.is_linux = self.platform == "linux"

        # Buffering for long/structured answers
        self._buffer_text = ""
        self._last_speech_ts = 0.0
        self._utterance_start_ts = 0.0
        # Adaptive silence thresholds
        self._short_silence_sec = 1.5   # acceptable pause within an utterance
        self._final_silence_sec = 3.3   # decisive end-of-utterance pause
        self._confirm_pause_sec = 0.7   # extra wait to confirm completion (default)
        self._pending_finalize_since = 0.0
        self._recalibrate_every_sec = 60.0
        self._last_recalibrate_ts = 0.0
        self._max_utterance_sec = 75.0  # hard cap to avoid waiting forever

    def run(self):
        if not HAVE_SPEECH_RECOGNITION:
            self.error.emit("Speech Recognition not available. Install 'speech_recognition'.")
            return
        try:
            self.running = True
            self.listening_status.emit("Initializing...")
            
            # Initialize recognizer and microphone with balanced, interview-friendly settings
            self.recognizer = sr.Recognizer()
            # Balanced settings per requirements
            self.recognizer.pause_threshold = 1.5
            self.recognizer.non_speaking_duration = 0.85
            self.recognizer.phrase_threshold = 0.08
            self.recognizer.dynamic_energy_threshold = True
            
            # Microphone selection (best available)
            try:
                mic_list = sr.Microphone.list_microphone_names()
                
                def is_virtual(name: str) -> bool:
                    n = name.lower()
                    virtual_terms = [
                        'virtual', 'vb-audio', 'cable', 'stereo mix', 'mix', 'loopback',
                        'what u hear', 'what-you-hear', 'wave out', 'output', 'speaker',
                        'monitor of', 'line (voicemeeter', 'ndis', 'aux'
                    ]
                    return any(t in n for t in virtual_terms)

                def score_device(name: str) -> int:
                    n = name.lower()
                    score = 0
                    if any(k in n for k in ['mic', 'microphone', 'array', 'headset']):
                        score += 100
                    if 'usb' in n:
                        score += 50
                    if any(k in n for k in ['realtek', 'intel', 'high definition audio', 'built-in', 'internal']):
                        score += 20
                    if 'headphones' in n and 'mic' not in n and 'microphone' not in n:
                        score -= 60
                    return score

                candidates = [
                    (idx, name, score_device(name))
                    for idx, name in enumerate(mic_list)
                    if not is_virtual(name)
                ]

                if candidates:
                    best = max(candidates, key=lambda x: x[2])
                    chosen_index = best[0]
                    self.microphone = sr.Microphone(device_index=chosen_index)
                else:
                    self.microphone = sr.Microphone()
            except Exception:
                # Fallback to default microphone
                self.microphone = sr.Microphone()
            
            # Initial ambient noise calibration
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
            except Exception:
                pass
            self._last_recalibrate_ts = time.time()
            self._utterance_start_ts = 0.0
            
            self.listening_status.emit("Ready! Speak now!")
            
            # Continuous loop: short timeout for start-of-speech detection, no phrase limit
            while self.running:
                try:
                    now = time.time()
                    # Periodic re-calibration in long sessions
                    if now - self._last_recalibrate_ts > self._recalibrate_every_sec:
                        try:
                            with self.microphone as source:
                                self.listening_status.emit("Adjusting for ambient noise...")
                                self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
                            self._last_recalibrate_ts = time.time()
                        except Exception:
                            pass

                    with self.microphone as source:
                        self.listening_status.emit("Listening...")
                        # Short timeout to detect start of speech quickly, no phrase limit to allow long answers
                        audio = self.recognizer.listen(
                            source,
                            timeout=0.9,
                            phrase_time_limit=None,
                            snowboy_configuration=None
                        )
                    
                    if not self.running:
                        break
                        
                    self.listening_status.emit("Processing...")
                    
                    text = ""
                    # Google first with alternatives
                    try:
                        result = self.recognizer.recognize_google(audio, language=self.language, show_all=True)
                        if isinstance(result, dict) and 'alternative' in result:
                            best_alt = None
                            best_score = -1.0
                            for alt in result['alternative']:
                                transcript = alt.get('transcript', '')
                                conf = float(alt.get('confidence', 0.0)) if 'confidence' in alt else 0.0
                                score = conf if conf > 0 else (len(transcript) / 120.0)
                                if transcript and score > best_score:
                                    best_score = score
                                    best_alt = transcript
                            if best_alt:
                                text = best_alt
                        elif isinstance(result, str):
                            text = result
                        else:
                            # fallback: try non-show_all
                            text = self.recognizer.recognize_google(audio, language=self.language, show_all=False)
                    except sr.UnknownValueError:
                        # Try Sphinx as offline fallback
                        try:
                            text = self.recognizer.recognize_sphinx(audio, language=self.language)
                        except Exception:
                            text = ""
                    except sr.RequestError:
                        # Network issue, try Sphinx
                        try:
                            text = self.recognizer.recognize_sphinx(audio, language=self.language)
                        except Exception:
                            text = ""
                    except Exception:
                        text = ""
                    
                    text = (text or "").strip()
                    if text:
                        # Start utterance timing on first segment
                        if self._utterance_start_ts == 0.0:
                            self._utterance_start_ts = time.time()
                        # Update buffer and timestamp; avoid naive duplicate concatenation
                        if self._buffer_text:
                            self._buffer_text = self._merge_transcript(self._buffer_text, text)
                        else:
                            self._buffer_text = text
                        self._last_speech_ts = time.time()
                        # Any new speech cancels pending finalization
                        self._pending_finalize_since = 0.0
                        self.listening_status.emit("Captured segment...")
                    
                    # Decide whether to finalize based on silence and utterance characteristics
                    self._maybe_finalize()
                    
                except sr.WaitTimeoutError:
                    # No speech detected during this short window; check finalize conditions
                    self._maybe_finalize()
                    if not self._buffer_text:
                        self.listening_status.emit("Listening...")
                    continue
                except sr.UnknownValueError:
                    # Inaudible; keep listening but also check if buffer should finalize
                    self._maybe_finalize()
                    continue
                except sr.RequestError as e:
                    self.listening_status.emit("Service error, retrying...")
                    continue
                except Exception as e:
                    self.listening_status.emit("Error, retrying...")
                    continue
                    
        except Exception as e:
            self.error.emit(f"Failed to initialize speech recognition: {e}")

    def _maybe_finalize(self):
        now = time.time()
        has_buffer = bool(self._buffer_text and self._last_speech_ts > 0)
        if not has_buffer:
            return
        silence = now - self._last_speech_ts
        utterance_duration = (now - self._utterance_start_ts) if self._utterance_start_ts > 0 else 0.0
        words = len(self._buffer_text.split())
        ends_sentence = any(self._buffer_text.strip().endswith(p) for p in ["?", ".", "!", ":"]) or \
                        any(k in self._buffer_text.lower() for k in ["thank you", "that's it", "that's all"]) 
        # Fast-path for short questions
        txt_lower = self._buffer_text.strip().lower()
        question_starters = (
            "what ", "why ", "how ", "is ", "are ", "can ", "does ", "do ", "did ",
            "will ", "would ", "should ", "could ", "tell me ", "explain ", "when ", "where ", "which "
        )
        starts_like_question = any(txt_lower.startswith(qw) for qw in question_starters)
        ends_qmark = txt_lower.endswith("?")
        is_short_question = (words <= 8) or starts_like_question or ends_qmark

        # Finalization policy with confirmation window:
        # - If long utterance (>= 10 words) and pause >= short_silence -> candidate finalize
        # - If clear sentence/question end and pause >= 1.0s -> candidate finalize
        # - If strong pause >= final_silence regardless of length -> candidate finalize
        # - If max utterance duration exceeded -> candidate finalize
        candidate = (
            (words >= 10 and silence >= self._short_silence_sec) or
            (ends_sentence and silence >= 0.75) or
            (silence >= self._final_silence_sec) or
            (utterance_duration >= self._max_utterance_sec)
        )
        # Short-question candidate: finalize faster after ~0.9s pause
        candidate_short = is_short_question and (silence >= 0.55)
        candidate = candidate or candidate_short

        if candidate:
            # Start or check confirmation window
            if self._pending_finalize_since == 0.0:
                self._pending_finalize_since = now
                # Inform user we're waiting for completion
                self.listening_status.emit("Waiting for question completion…")
                return
            # Shorter confirmation window for short questions
            confirm_hold = 0.22 if is_short_question else self._confirm_pause_sec
            if (now - self._pending_finalize_since) < confirm_hold:
                # Still confirming
                return

            # Confirmed finalize
            final_text = self._buffer_text.strip()
            self._buffer_text = ""
            self._utterance_start_ts = 0.0
            self._pending_finalize_since = 0.0
            if final_text:
                self.recognized.emit(final_text)
                self.listening_status.emit("Got it!")

    def _merge_transcript(self, existing: str, new_part: str) -> str:
        """Merge ASR segments, removing simple overlaps to improve accuracy."""
        existing = existing.strip()
        new_part = new_part.strip()
        if not existing:
            return new_part
        if not new_part:
            return existing
        # If new part is fully contained, keep existing
        if new_part in existing:
            return existing
        # If existing is contained in new part, take new
        if existing in new_part:
            return new_part
        # Attempt overlap merge based on suffix/prefix match
        max_overlap = min(20, len(existing), len(new_part))
        for k in range(max_overlap, 0, -1):
            if existing.endswith(new_part[:k]):
                return (existing + new_part[k:]).strip()
        # No overlap: concatenate with space
        return (existing + " " + new_part).strip()

    def stop(self):
        self.running = False
        # If there's buffered speech, emit it once on stop
        if self._buffer_text:
            final_text = self._buffer_text.strip()
            self._buffer_text = ""
            self._utterance_start_ts = 0.0
            if final_text:
                self.recognized.emit(final_text)


class AuthView(QWidget):
    authed = Signal(str, str, int)  # email, password, credits

    def __init__(self):
        super().__init__()
        self.setStyleSheet(glass())
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # No header for login UI, just the login box

        body = QFrame()
        body.setStyleSheet(glass_panel("rgba(0,0,0,0.7)"))
        body.setFixedSize(340, 200)  # Slightly bigger for better text visibility
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)  # More padding for comfort
        body_layout.setSpacing(6)

        self.email = QLineEdit()
        self.email.setPlaceholderText("Email")
        self.email.setStyleSheet(input_style())
        self.pw = QLineEdit()
        self.pw.setPlaceholderText("Password")
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setStyleSheet(input_style())

        self.status = QLabel("")
        self.status.setStyleSheet("color:#fff; font-style: italic;")
        self.status.setWordWrap(True)

        self.btn_login = QPushButton("Login")
        self.btn_login.setStyleSheet(button_primary())
        self.btn_login.clicked.connect(self._login)

        self.btn_signup = QPushButton("New user? Sign up")
        self.btn_signup.setStyleSheet("""
            QPushButton { background: transparent; color: #4F8CFF; border: none; }
            QPushButton:hover { text-decoration: underline; }
        """)
        self.btn_signup.clicked.connect(self._signup)

        body_layout.addWidget(self.email)
        body_layout.addWidget(self.pw)
        body_layout.addWidget(self.btn_login)
        body_layout.addWidget(self.btn_signup)
        body_layout.addWidget(self.status)

        # Center the login box in the window
        root.addStretch(1)
        hbox = QHBoxLayout()
        hbox.addStretch(1)
        hbox.addWidget(body)
        hbox.addStretch(1)
        root.addLayout(hbox)
        root.addStretch(1)

        # auto-fill from local file if exists
        self._try_autologin()

    def _try_autologin(self):
        f = os.path.expanduser("~/.live_insights_session.json")
        if os.path.exists(f):
            try:
                with open(f, "r") as fp:
                    d = json.load(fp)
                if time.time() - d.get("ts", 0) < 7 * 24 * 3600:
                    self.email.setText(d.get("email", ""))
                    self.pw.setText(d.get("password", ""))
                    self._login(auto=True)
            except Exception:
                pass

    def _login(self, auto=False):
        em = self.email.text().strip()
        pw = self.pw.text().strip()
        if not em or not pw:
            QMessageBox.warning(self, "Login", "Please enter both email and password.")
            return
        self.status.setText("Logging in...")
        QApplication.processEvents()
        try:
            r = requests.post(f"{BACKEND_URL}/login", json={"email": em, "password": pw}, timeout=8)
            j = r.json()
            if j.get("success"):
                # fetch credits
                gc = requests.post(f"{BACKEND_URL}/get_credits", json={"email": em, "password": pw}, timeout=8).json()
                credits = gc.get("credits", 0)
                # store session for 7 days
                with open(os.path.expanduser("~/.live_insights_session.json"), "w") as fp:
                    json.dump({"email": em, "password": pw, "ts": time.time()}, fp)
                self.authed.emit(em, pw, credits)
            else:
                self.status.setText(j.get("message", "Login failed."))
        except Exception as e:
            self.status.setText(f"Error: {e}")

    def _signup(self):
        em = self.email.text().strip()
        pw = self.pw.text().strip()
        if not em or not pw:
            QMessageBox.warning(self, "Signup", "Please enter both email and password.")
            return
        self.status.setText("Signing up...")
        QApplication.processEvents()
        try:
            r = requests.post(f"{BACKEND_URL}/signup", json={"email": em, "password": pw}, timeout=8)
            j = r.json()
            if j.get("success"):
                QMessageBox.information(self, "Signup", "Account created! Please log in.")
            else:
                self.status.setText(j.get("message", "Signup failed."))
        except Exception as e:
            self.status.setText(f"Error: {e}")


class MainView(QWidget):
    # Marshal background-thread updates safely to the UI thread
    ai_update = Signal(dict)
    request_logout = Signal()

    def __init__(self, email, password, credits):
        super().__init__()
        self.email = email
        self.password = password
        self.credits = int(credits or 0)

        self.questions = []
        self.answers = []
        self.ai_response = ""
        self.smart_mode = False
        self.resume_path = None
        self.listening = False
        self.opacity = 0.95
        
        # Credit system: 1 credit for every 2 answers
        self.answer_count = 0
        self.answers_since_last_credit = 0
        
        # Platform detection for optimizations
        self.platform = platform.system().lower()
        self.is_windows = self.platform == "windows"
        self.is_macos = self.platform == "darwin"
        self.is_linux = self.platform == "linux"

        self.listener = None  # WhisperThread
        self._drag_pos = None

        self.setStyleSheet(glass())

        # Connect background updates to UI-thread slot
        self.ai_update.connect(self._apply_ai_update)

        # Persistent HTTP session for faster requests
        self._session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.2, status_forcelist=[429, 502, 503, 504])
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=retries)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._build()
        self._install_hotkeys()

    def _build(self):
        self.setMinimumSize(800, 400)
        self.resize(900, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setStyleSheet(header_style())
        header.setFixedHeight(40)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 16, 8)
        hl.setSpacing(10)

        self.drag_handle = QLabel("💡  Live insights")
        self.drag_handle.setStyleSheet("font-weight: 700; font-size: 16px;")
        self.drag_handle.setToolTip("Click and drag to move window")
        hl.addWidget(self.drag_handle)

        self.smart_label = QLabel("Smart mode: OFF")
        self.smart_label.setStyleSheet("color: #aaa; font-size: 14px;")
        hl.addWidget(self.smart_label)

        hl.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.credit_label = QLabel(f"Credits: {self.credits} ")
        self.credit_label.setStyleSheet("color: #4CAF50; font-weight: 700;")
        hl.addWidget(self.credit_label)

    # Removed the close (cross) button from the main header

        btn_logout = QPushButton("Logout")
        btn_logout.setStyleSheet("QPushButton{background: transparent; color: #fff; border: none; font-weight: 600;}")
        btn_logout.clicked.connect(self._logout)
        hl.addWidget(btn_logout)

        root.addWidget(header)

        # Main card
        card = QFrame()
        card.setStyleSheet(glass_panel())
        cl = QHBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Left (Questions + controls)
        left = QFrame()
        left.setStyleSheet("background-color: rgba(35,35,35,0.85); border-right: 1px solid #333;")
        left.setMinimumWidth(300)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(8)

        qh = QLabel("Questions")
        qh.setStyleSheet("font-weight: 600; font-size: 15px;")
        ll.addWidget(qh)

        self.questions_box = QTextEdit()
        self.questions_box.setReadOnly(True)
        self.questions_box.setWordWrapMode(QTextOption.WordWrap)
        self.questions_box.setStyleSheet(textedit_style())
        ll.addWidget(self.questions_box, 1)

        # Listening controls
        listen_controls = QHBoxLayout()
        
        self.btn_listen = QPushButton("🎤 Start Listening")
        self.btn_listen.setStyleSheet(button_primary())
        self.btn_listen.clicked.connect(self._toggle_listening)
        listen_controls.addWidget(self.btn_listen)
        
        # Add microphone status indicator
        self.mic_status = QLabel("🎤 Microphone: Ready")
        self.mic_status.setStyleSheet("color:#4CAF50; font-size:12px; font-weight:600;")
        listen_controls.addWidget(self.mic_status)
        
        ll.addLayout(listen_controls)

        self.listen_status = QLabel("Click to start listening")
        self.listen_status.setStyleSheet("color:#4CAF50; font-weight:700;")
        ll.addWidget(self.listen_status)

        # Remove manual input section - keeping it simple

        self.resume_status = QLabel("")
        self.resume_status.setStyleSheet("color:#4CAF50; font-weight:600;")
        ll.addWidget(self.resume_status)

        # Platform-specific hotkey tips
        if self.is_windows:
            smart_key = "Alt+Shift+S"
            resume_key = "Alt+Shift+R"
            hide_key = "Alt+Shift+H"
        elif self.is_macos:
            smart_key = "Cmd+Shift+S"
            resume_key = "Cmd+Shift+R"
            hide_key = "Cmd+Shift+H"
        else:
            smart_key = "Alt+Shift+S"
            resume_key = "Alt+Shift+R"
            hide_key = "Alt+Shift+H"
        
        tips = QLabel(
            f"🎤 Voice: Click to listen | 📋 Smart: {smart_key} | 📄 Upload: {resume_key}\n"
            f"🖱️ Drag: Click anywhere to move| ⌨️ Hide/Show: {hide_key}\n"
            "💡 Smart Mode: Uses resume context for personalized answers\n"
            f" 🖥️ Platform: {self.platform.title()}"
        )
        tips.setStyleSheet("color:#aaa; font-size: 10px; line-height: 1.2; padding: 4px;")
        ll.addWidget(tips)

        # Right (Answers)
        right = QFrame()
        right.setStyleSheet("background-color: rgba(35,35,35,0.85);")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(8)

        ah = QLabel("Answers")
        ah.setStyleSheet("font-weight: 600; font-size: 15px;")
        rl.addWidget(ah)

        self.answers_box = QTextEdit()
        self.answers_box.setReadOnly(True)
        self.answers_box.setWordWrapMode(QTextOption.WordWrap)
        # Special interview-friendly styling for answers
        self.answers_box.setStyleSheet("""
            QTextEdit {
                background: rgba(40,40,40,0.95);
                border: none;
                border-radius: 10px;
                color: #fff;
                padding: 16px;
                line-height: 1.8;
                font-size: 15px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: 500;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.1);
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.3);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.5);
            }
        """)
        rl.addWidget(self.answers_box, 1)

        cl.addWidget(left, 1)
        cl.addWidget(right, 1)

        root.addWidget(card, 1)

        # Add resize handle in bottom-right corner
        self.resize_handle = QFrame()
        self.resize_handle.setFixedSize(20, 20)
        self.resize_handle.setStyleSheet("""
                    QFrame {
            background-color: rgba(255,255,255,0.2);
            border-radius: 10px;
        }
        QFrame:hover {
            background-color: rgba(255,255,255,0.4);
        }
        """)
        self.resize_handle.mousePressEvent = self._start_resize
        self.resize_handle.mouseMoveEvent = self._resize_window
        
        # Position resize handle in bottom-right
        resize_layout = QHBoxLayout()
        resize_layout.addStretch()
        resize_layout.addWidget(self.resize_handle)
        root.addLayout(resize_layout)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            try:
                pos = e.globalPosition().toPoint()
            except AttributeError:
                pos = e.globalPos()
            self._drag_pos = pos - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
        else:
            e.ignore()
    
    def mouseReleaseEvent(self, e):
        """Handle mouse release for both dragging and resizing"""
        # Handle dragging
        if self._drag_pos is not None:
            self._drag_pos = None
            self.setCursor(Qt.ArrowCursor)
        
        # Handle resizing
        if hasattr(self, '_resize_start_pos'):
            delattr(self, '_resize_start_pos')
            delattr(self, '_resize_start_size')
            self.setCursor(Qt.ArrowCursor)
        
        e.accept()
    
    def mouseDoubleClickEvent(self, e):
        """Double-click to toggle window size between default and full screen"""
        if e.button() == Qt.LeftButton:
            if self.size() == QSize(900, 500):
                # Expand to larger size
                self.resize(1200, 700)
            else:
                # Return to default size
                self.resize(900, 500)
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos is not None:
            try:
                pos = e.globalPosition().toPoint()
            except AttributeError:
                pos = e.globalPos()
            self.move(pos - self._drag_pos)
            e.accept()


    
    def _start_resize(self, e):
        """Start resizing the window"""
        if e.button() == Qt.LeftButton:
            self._resize_start_pos = e.globalPosition().toPoint()
            self._resize_start_size = self.size()
            self.setCursor(Qt.SizeFDiagCursor)
            e.accept()
    
    def _resize_window(self, e):
        """Resize the window based on mouse movement"""
        if hasattr(self, '_resize_start_pos') and hasattr(self, '_resize_start_size'):
            delta = e.globalPosition().toPoint() - self._resize_start_pos
            new_width = max(800, self._resize_start_size.width() + delta.x())
            new_height = max(400, self._resize_start_size.height() + delta.y())
            self.resize(new_width, new_height)
            e.accept()
    
    def mouseReleaseEvent(self, e):
        """Handle mouse release for both dragging and resizing"""
        # Handle dragging
        if self._drag_pos is not None:
            self._drag_pos = None
            self.setCursor(Qt.ArrowCursor)
        
        # Handle resizing
        if hasattr(self, '_resize_start_pos'):
            delattr(self, '_resize_start_pos')
            delattr(self, '_resize_start_size')
            self.setCursor(Qt.ArrowCursor)
        
        e.accept()

    def _hide_self(self):
        # Platform-specific hide/show with appropriate hotkey display
        if self.is_windows:
            hide_key = "Alt+Shift+H"
        elif self.is_macos:
            hide_key = "Cmd+Shift+H"
        else:
            hide_key = "Alt+Shift+H"
        
        # Toggle between hide and show
        if self.isVisible():
            self.hide()
            # Store position before hiding for restoration
            self._stored_pos = self.pos()
            self.listen_status.setText(f"Window hidden. Press {hide_key} to show.")
        else:
            self.show()
            # Restore position if we have a stored one
            if hasattr(self, '_stored_pos'):
                self.move(self._stored_pos)
            self.raise_()
            self.activateWindow()
            self.listen_status.setText("Window shown.")

    def _logout(self):
        # mirror React: clear local + call /logout
        try:
            requests.post(f"{BACKEND_URL}/logout", timeout=3)
        except Exception:
            pass
        # delete session file
        try:
            os.remove(os.path.expanduser("~/.live_insights_session.json"))
        except Exception:
            pass
        self.request_logout.emit()

    def _install_hotkeys(self):
        """Install platform-specific hotkeys with error handling"""
        try:
            # Platform-specific hotkey setup
            if self.is_windows:
                # Windows: Alt+Shift combinations
                smart_key = "Alt+Shift+S"
                resume_key = "Alt+Shift+R"
                clear_key = "Alt+Shift+C"
                quit_key = "Alt+Shift+Q"
                listen_key = "Alt+Shift+L"
                test_key = "Alt+Shift+T"
            elif self.is_macos:
                # macOS: Cmd+Shift combinations (more native)
                smart_key = "Ctrl+Shift+S"
                resume_key = "Ctrl+Shift+R"
                clear_key = "Ctrl+Shift+C"
                quit_key = "Ctrl+Shift+Q"
                listen_key = "Ctrl+Shift+L"
                test_key = "Ctrl+Shift+T"
            else:
                # Linux: Alt+Shift combinations
                smart_key = "Alt+Shift+S"
                resume_key = "Alt+Shift+R"
                clear_key = "Alt+Shift+C"
                quit_key = "Alt+Shift+Q"
                listen_key = "Alt+Shift+L"
                test_key = "Alt+Shift+T"
            
            # Smart mode toggle
            sc_s = QShortcut(QKeySequence(smart_key), self)
            sc_s.activated.connect(self._toggle_smart)

            # Upload resume
            sc_r = QShortcut(QKeySequence(resume_key), self)
            sc_r.activated.connect(self._upload_resume)

            # Clear answers
            sc_c = QShortcut(QKeySequence(clear_key), self)
            sc_c.activated.connect(self._clear_answers)

            # Quit application
            sc_q = QShortcut(QKeySequence(quit_key), self)
            sc_q.activated.connect(QApplication.quit)

            # Start listening
            sc_l = QShortcut(QKeySequence(listen_key), self)
            sc_l.activated.connect(self._toggle_listening)
            
            # Test hotkey
            sc_test = QShortcut(QKeySequence(test_key), self)
            sc_test.activated.connect(self._test_hotkey)
            
            # Store shortcuts for potential cleanup
            self._hotkeys = [sc_s, sc_r, sc_c, sc_q, sc_l, sc_test]
            
        except Exception as e:
            # Fallback to basic hotkeys if platform-specific ones fail
            try:
                # Basic fallback hotkeys
                sc_s = QShortcut(QKeySequence("Ctrl+S"), self)
                sc_s.activated.connect(self._toggle_smart)
                
                sc_r = QShortcut(QKeySequence("Ctrl+R"), self)
                sc_r.activated.connect(self._upload_resume)
                
                sc_l = QShortcut(QKeySequence("Ctrl+L"), self)
                sc_l.activated.connect(self._toggle_listening)
                
                self._hotkeys = [sc_s, sc_r, sc_l]
                
            except Exception as fallback_error:
                # If even fallback fails, just continue without hotkeys
                pass

    def _install_hide_hotkey(self):
        pass  # No-op, handled globally in MainWindow

    def _toggle_smart(self):
        if not self.resume_path:
            QMessageBox.information(self, "Smart mode", "Please upload a resume before enabling Smart mode.")
            self.smart_mode = False
        else:
            self.smart_mode = not self.smart_mode
        self.smart_label.setText(f"Smart mode: {'ON' if self.smart_mode else 'OFF'}")
        self.smart_label.setStyleSheet(f"color: {'#4CAF50' if self.smart_mode else '#aaa'}; font-size:14px;")

    def _upload_resume(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Upload Resume", 
            os.path.expanduser("~"), 
            "Documents (*.pdf *.txt *.doc *.docx);;PDF Files (*.pdf);;Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
            
        # Check file size (limit to 10MB)
        file_size = os.path.getsize(path) / (1024 * 1024)  # Convert to MB
        if file_size > 10:
            QMessageBox.warning(self, "File Too Large", "Please select a file smaller than 10MB.")
            return
            
        # Show processing status
        self.resume_status.setText("🔄 Processing resume...")
        self.resume_status.setStyleSheet("color:#FFA500; font-weight:600;")
        QApplication.processEvents()
        
        try:
            # Try to read a preview of the resume content
            resume_preview = self._get_resume_preview(path)
            if resume_preview:
                self.resume_path = path
                filename = os.path.basename(path)
                self.resume_status.setText(f"✅ Resume loaded: {filename}\n📄 Content preview: {resume_preview[:100]}...")
                self.resume_status.setStyleSheet("color:#4CAF50; font-weight:600; font-size:12px;")
                
                # Auto-enable smart mode if resume is loaded
                if not self.smart_mode:
                    self.smart_mode = True
                    self.smart_label.setText("Smart mode: ON")
                    self.smart_label.setStyleSheet("color: #4CAF50; font-size:14px;")
            else:
                self.resume_status.setText("❌ Could not read resume content")
                self.resume_status.setStyleSheet("color:#f44336; font-weight:600;")
                
        except Exception as e:
            self.resume_status.setText(f"❌ Error processing resume: {str(e)}")
            self.resume_status.setStyleSheet("color:#f44336; font-weight:600;")

    def _get_resume_preview(self, file_path):
        """Get a preview of resume content for validation"""
        try:
            if file_path.lower().endswith('.pdf'):
                # For PDFs, we'll just check if the file can be opened
                # The actual text extraction will be done by the backend
                return "PDF file detected - content will be extracted by backend"
            else:
                # For text files, read a preview
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if len(content.strip()) > 0:
                        return content.strip()
                    else:
                        return None
        except Exception as e:
            return None
    
    def _clear_answers(self):
        self.answers = []
        self.answers_box.clear()
    
    def _test_hotkey(self):
        """Test method to verify hotkeys are working"""
        QMessageBox.information(self, "Hotkey Test", "Hotkey system is working! Alt+Shift+T pressed.")

    # mic test code removed

    def _toggle_listening(self):
        if not HAVE_SPEECH_RECOGNITION:
            QMessageBox.warning(self, "Listening", "Speech not available. Install 'speech_recognition'.")
            return

        if self.listening:
            # Stop listening
            self.listening = False
            self.btn_listen.setText("🎤 Start Listening")
            self.btn_listen.setStyleSheet(button_primary())
            self.listen_status.setText("Stopped listening.")
            self.mic_status.setText("🎤 Microphone: Ready")
            self.mic_status.setStyleSheet("color:#4CAF50; font-size:12px; font-weight:600;")
            if self.listener:
                self.listener.stop()
                self.listener.quit()
                self.listener = None
        else:
            # Start listening
            self.listening = True
            self.btn_listen.setText("⏹️ Stop Listening")
            self.btn_listen.setStyleSheet("""
                QPushButton {
                    background: rgba(239,68,68,0.9);
                    color: white;
                    font-weight: 700;
                    border: none;
                    border-radius: 24px;
                    padding: 10px 16px;
                }
                QPushButton:hover {
                    background: rgba(239,68,68,1);
                }
                QPushButton:disabled {
                    background: #2b2b2b;
                    color: #888;
                }
            """)
            self.listen_status.setText("Starting...")
            self.mic_status.setText("🎤 Microphone: Starting...")
            self.mic_status.setStyleSheet("color:#FFA500; font-size:12px; font-weight:600;")
            
            # Create and start speech recognition thread
            try:
                self.listener = SpeechRecognitionThread(language="en-US", parent=self)
                self.listener.recognized.connect(self._on_speech)
                self.listener.error.connect(self._on_listen_error)
                self.listener.listening_status.connect(self._on_listening_status)
                self.listener.start()
            except Exception as e:
                self.listen_status.setText(f"Failed to start: {str(e)}")
                self.mic_status.setText("🎤 Microphone: Error ❌")
                self.mic_status.setStyleSheet("color:#f44336; font-size:12px; font-weight:600;")
                self.listening = False
                self.btn_listen.setText("🎤 Start Listening")
                self.btn_listen.setStyleSheet(button_primary())

    def _on_listen_error(self, msg):
        self.listen_status.setText(f"Error: {msg}")
        self.listening = False
        self.btn_listen.setEnabled(True)
        self.btn_listen.setText("🎤 Start Listening")
        self.btn_listen.setStyleSheet(button_primary())
        if self.listener:
            self.listener.stop()
            self.listener.quit()
            self.listener = None

    def _on_listening_status(self, status):
        self.listen_status.setText(status)

    def _on_speech(self, text):
        # Accept ALL speech - no filtering or validation
        if not text or len(text.strip()) < 1:  # Only check if text exists
            return
        
        # Add the question to the list
        self.questions.insert(0, text.strip())
        self._render_questions()
        
        # Clear answers - thinking will be shown by _ask_ai
        self.answers_box.clear()
        
        # Send to AI immediately
        self._ask_ai(text.strip())
        
        # Automatically continue listening for the next question
        if self.listening and self.listener and self.listener.running:
            # The speech recognition thread will continue automatically
            self.listen_status.setText("Listening for next question...")

    def _render_questions(self):
        # newest first (matching your scroll-to-top in React)
        self.questions_box.clear()
        for i, q in enumerate(self.questions):
            # Format questions in a clean, interview-friendly way
            formatted_question = f"Q{i+1}: {q.strip()}"
            self.questions_box.append(formatted_question)
        
        # Auto-scroll to the latest question
        if self.questions:
            self.questions_box.verticalScrollBar().setValue(0)

    def _render_answers(self):
        self.answers_box.clear()
        for i, a in enumerate(self.answers):
            # Format answer in a systematic, interview-friendly way
            formatted_answer = self._format_answer_for_interview(a, i+1)
            self.answers_box.append(formatted_answer)
        
        # Auto-scroll to the latest answer for easy reading
        if self.answers:
            self.answers_box.verticalScrollBar().setValue(0)

    def _format_answer_for_interview(self, answer, answer_number):
        """Format AI response in a systematic, interview-friendly way"""
        if not answer or answer.strip() == "":
            return ""
            
        # Clean up the answer
        answer = answer.strip()
        
        # Check if it's an error message
        if any(error_indicator in answer.lower() for error_indicator in ["❌", "⏰", "🔌", "error", "timeout", "connection"]):
            return f"A{answer_number}: {answer}"
        
        # Format systematic responses
        formatted = f"A{answer_number}: "
        
        # Split into paragraphs
        paragraphs = answer.split('\n\n')
        
        for i, paragraph in enumerate(paragraphs):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # If paragraph starts with common interview response patterns, format them
            if any(pattern in paragraph.lower()[:50] for pattern in [
                "based on", "in my experience", "i would", "my approach", 
                "the key", "first", "second", "third", "finally",
                "here's how", "let me", "i believe", "my strategy"
            ]):
                # Format as structured response
                formatted += self._structure_paragraph(paragraph)
            else:
                # Regular paragraph
                formatted += paragraph
                
            # Add spacing between paragraphs
            if i < len(paragraphs) - 1:
                formatted += "\n\n"
        
        return formatted

    def _structure_paragraph(self, paragraph):
        """Structure a paragraph for better readability"""
        # Look for numbered or bullet points
        lines = paragraph.split('\n')
        structured = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for numbered lists (1., 2., etc.)
            if re.match(r'^\d+\.', line):
                structured += f"• {line[line.find('.')+1:].strip()}\n"
            # Check for bullet points
            elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
                structured += f"• {line[1:].strip()}\n"
            # Check for key phrases that should be highlighted
            elif any(keyword in line.lower() for keyword in [
                "key", "important", "critical", "essential", "main", "primary"
            ]):
                structured += f"🔑 {line}\n"
            # Check for action items
            elif any(action in line.lower() for action in [
                "would", "will", "should", "could", "might"
            ]):
                structured += f"→ {line}\n"
            else:
                structured += f"{line}\n"
        
        return structured.strip()

    def _render_ai_response(self):
        if self.ai_response:
            self.answers_box.append(self.ai_response)

    def _conversation_history(self, max_messages=6):
        # Interleave as in React; limit to recent to shrink payload
        hist = []
        q_rev = list(reversed(self.questions))[:max_messages]
        a_rev = list(reversed(self.answers))[:max_messages]
        for i in range(max(len(q_rev), len(a_rev))):
            if i < len(q_rev):
                hist.append({"role": "user", "content": q_rev[i]})
            if i < len(a_rev):
                hist.append({"role": "assistant", "content": a_rev[i]})
        return hist

    def _ask_ai(self, question):
        # mirrors askAI in React
        if self.credits <= 0:
            self.ai_response = "❌ No credits left. Please purchase more credits."
            self._render_answers()
            self._render_ai_response()
            return
            
        # Show thinking indicator
        self.ai_response = "🤔 Processing..."
        self._render_ai_response()
        QApplication.processEvents()  # Update UI immediately
        
        # offload network request to background to keep listening continuous
        _executor.submit(self._process_ai_request, question)

    def _process_ai_request(self, question):
        # prepare request (smart vs global)
        try:
            if self.smart_mode and self.resume_path:
                # smart: multipart with file
                files = {
                    "resume": (os.path.basename(self.resume_path), open(self.resume_path, "rb"),
                               "application/pdf" if self.resume_path.lower().endswith(".pdf") else "text/plain")
                }
                data = {
                    "question": question,
                    "email": self.email,
                    "mode": "resume",
                    "history": json.dumps(self._conversation_history())
                }
                # Inform UI from background via signal
                self.ai_update.emit({"listen_status": "🤖 Sending to AI (Smart Mode - Using Resume Context)..."})
                # Faster, persistent session with moderate timeout
                r = self._session.post(f"{BACKEND_URL}/ask", files=files, data=data, timeout=35)
                j = r.json()
                ans = j.get("answer") or "No response from AI."
                
                # Check if answer was blocked due to template detection
                if "[Error: The answer was blocked" in ans:
                    self.ai_update.emit({
                        "answers": [f"❌ {ans}"],
                        "ai_response": "",
                        "listen_status": "Answer blocked - please rephrase your question"
                    })
                elif "Could not extract any text" in ans:
                    self.ai_update.emit({
                        "answers": [f"❌ {ans}"],
                        "ai_response": "",
                        "smart_mode": False,
                        "smart_label_text": "Smart mode: OFF",
                        "smart_label_style": "color: #aaa; font-size:14px;",
                        "resume_status_text": "❌ Resume text extraction failed",
                        "resume_status_style": "color:#f44336; font-weight:600;"
                    })
                else:
                    # Success - answer based on resume context
                    self.ai_update.emit({
                        "answers": [ans],
                        "ai_response": "",
                        "listen_status": "✅ Resume-based answer received!"
                    })
                    # Deduct credit only for genuine answers in background
                    _executor.submit(self._deduct_credit_for_genuine_answer_bg)
            else:
                # Global mode
                self.ai_update.emit({"listen_status": "🌐 Sending to AI (Global Mode - General Interview Advice)..."})
                r = self._session.post(f"{BACKEND_URL}/ask",
                                  json={
                                      "question": question,
                                      "email": self.email,
                                      "resume": "",
                                      "mode": "global",
                                      "history": self._conversation_history(max_messages=6)
                                  }, timeout=20)
                j = r.json()
                ans = j.get("answer") or "No response from AI."
                
                if "[Error: The answer was blocked" in ans:
                    self.ai_update.emit({
                        "answers": [f"❌ {ans}"],
                        "ai_response": "",
                        "listen_status": "Answer blocked - please rephrase your question"
                    })
                else:
                    self.ai_update.emit({
                        "answers": [ans],
                        "ai_response": "",
                        "listen_status": "✅ General interview advice received!"
                    })
                    _executor.submit(self._deduct_credit_for_genuine_answer_bg)
                
            self.ai_update.emit({"listen_status": "Response received!"})
            
        except requests.exceptions.Timeout:
            self.ai_update.emit({
                "answers": ["⏰ Request timed out. Please try again."],
                "ai_response": "",
                "listen_status": "Timeout error"
            })
        except requests.exceptions.ConnectionError:
            self.ai_update.emit({
                "answers": ["🔌 Connection error. Please check if the backend server is running."],
                "ai_response": "",
                "listen_status": "Connection error"
            })
        except Exception as e:
            self.ai_update.emit({
                "answers": [f"❌ Error: {str(e)}"],
                "ai_response": "",
                "listen_status": "Error occurred"
            })

    def _apply_ai_update(self, data):
        """Apply updates coming from background threads on the UI thread."""
        if not isinstance(data, dict):
            return
        if "listen_status" in data:
            self.listen_status.setText(data["listen_status"])
        if "ai_response" in data:
            self.ai_response = data["ai_response"]
        if "answers" in data:
            self.answers = data["answers"]
            self._render_answers()
        if "smart_mode" in data:
            self.smart_mode = bool(data["smart_mode"]) 
        if "smart_label_text" in data:
            self.smart_label.setText(data["smart_label_text"]) 
        if "smart_label_style" in data:
            self.smart_label.setStyleSheet(data["smart_label_style"]) 
        if "resume_status_text" in data:
            self.resume_status.setText(data["resume_status_text"]) 
        if "resume_status_style" in data:
            self.resume_status.setStyleSheet(data["resume_status_style"]) 
        if "credits" in data:
            self.credits = int(data["credits"]) 
        if "credit_label_text" in data:
            self.credit_label.setText(data["credit_label_text"]) 
        if "answers_since_last_credit" in data:
            self.answers_since_last_credit = int(data["answers_since_last_credit"]) 

    def _deduct_credit_for_genuine_answer_bg(self):
        """Background-safe credit deduction; emits UI updates instead of touching widgets."""
        # increment locally and prepare UI update for progress
        new_count = self.answers_since_last_credit + 1
        if new_count < 2:
            self.ai_update.emit({
                "answers_since_last_credit": new_count,
                "credit_label_text": f"Credits: {self.credits} ({2 - new_count} more answer(s) for next credit)"
            })
            return

        # Reached 2 answers: attempt to deduct on backend
        try:
            r = requests.post(f"{BACKEND_URL}/use_credit",
                              json={"email": self.email, "password": self.password},
                              timeout=8)
            j = r.json()
            if j.get("success") and isinstance(j.get("credits"), int):
                new_credits = j["credits"]
            else:
                gc = requests.post(f"{BACKEND_URL}/get_credits",
                                   json={"email": self.email, "password": self.password},
                                   timeout=8).json()
                new_credits = gc.get("credits", 0)
            # Emit UI updates
            self.ai_update.emit({
                "credits": new_credits,
                "credit_label_text": f"Credits: {new_credits} (1 credit for 2 answers)",
                "answers_since_last_credit": 0
            })
        except Exception:
            try:
                gc = requests.post(f"{BACKEND_URL}/get_credits",
                                   json={"email": self.email, "password": self.password},
                                   timeout=8).json()
                new_credits = gc.get("credits", 0)
                self.ai_update.emit({
                    "credits": new_credits,
                    "credit_label_text": f"Credits: {new_credits} (1 credit for 2 answers)",
                    "answers_since_last_credit": 0
                })
            except Exception:
                self.ai_update.emit({
                    "credit_label_text": "Credits: Error"
                })

    def _deduct_credit(self):
        """Legacy method - kept for compatibility"""
        _executor.submit(self._deduct_credit_for_genuine_answer_bg)




class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live insights - PySide")
        
        # Platform-specific window settings
        self.platform = platform.system().lower()
        self.is_windows = self.platform == "windows"
        self.is_macos = self.platform == "darwin"
        self.is_linux = self.platform == "linux"
        
        # Frameless but allows free movement and resizing
        if self.is_windows:
            # Windows: Full frameless with transparency
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setWindowOpacity(0.95)
        elif self.is_macos:
            # macOS: Frameless with title bar for better compatibility
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setWindowOpacity(0.95)
        else:
            # Linux: Standard frameless
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setWindowOpacity(0.95)

        self.stack = QStackedWidget()
        self.auth = AuthView()
        self.auth.authed.connect(self._on_authed)
        self.stack.addWidget(self.auth)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        # Set default size and position, but allow free movement and resizing
        self.resize(900, 500)
        self.move(60, 60)
        
        # Enable free window movement and resizing
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Install global hotkey for hide/unhide that works even when window is hidden
        self._install_global_hotkey()

    def _on_authed(self, email, password, credits):
        self.main = MainView(email, password, credits)
        self.main.request_logout.connect(self._back_to_login)
        if self.stack.count() == 2:
            self.stack.removeWidget(self.stack.widget(1))
        self.stack.addWidget(self.main)
        self.stack.setCurrentWidget(self.main)

    # Install global hotkey for hide/unhide that works even when hidden

    def _back_to_login(self):
        # clear session file already in MainView
        self.stack.setCurrentWidget(self.auth)
    
    def _install_global_hotkey(self):
        """Install platform-specific global hotkeys"""
        if self.is_windows:
            # Windows: Use Alt+Shift+H
            self.global_hide_hotkey = QShortcut(QKeySequence("Alt+Shift+H"), self)
        elif self.is_macos:
            # macOS: Use Cmd+Shift+H (more native)
            self.global_hide_hotkey = QShortcut(QKeySequence("Ctrl+Shift+H"), self)
        else:
            # Linux: Use Alt+Shift+H
            self.global_hide_hotkey = QShortcut(QKeySequence("Alt+Shift+H"), self)
        
        self.global_hide_hotkey.activated.connect(self._global_hide_unhide)
    
    def _global_hide_unhide(self):
        """Global hotkey handler for hide/unhide"""
        if hasattr(self, 'main'):
            self.main._hide_self()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Live insights")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
