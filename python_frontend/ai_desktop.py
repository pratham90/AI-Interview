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

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QAction, QShortcut, QKeySequence, QTextOption
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QFileDialog, QStackedWidget, QFrame, QMessageBox, QSizePolicy, QSpacerItem,
    QSlider
)

BACKEND_URL = "http://127.0.0.1:5000"

HAVE_SPEECH_RECOGNITION = True
try:
    import speech_recognition as sr
except Exception:
    HAVE_SPEECH_RECOGNITION = False

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
        cursor: move;
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

    def run(self):
        if not HAVE_SPEECH_RECOGNITION:
            self.error.emit("Speech Recognition not available. Install 'speech_recognition'.")
            return
        try:
            self.running = True
            self.listening_status.emit("Initializing speech recognition...")
            
            # Initialize recognizer and microphone with better noise handling
            self.recognizer = sr.Recognizer()
            
            # Try to get available microphones and choose a real input
            try:
                mic_list = sr.Microphone.list_microphone_names()
                print(f"[DEBUG] Available microphones: {mic_list}")

                def is_virtual(name: str) -> bool:
                    n = name.lower()
                    virtual_terms = [
                        'virtual', 'vb-audio', 'cable', 'stereo mix', 'mix', 'loopback',
                        'what u hear', 'what-you-hear', 'wave out', 'output', 'speaker',
                        'monitor of', 'line (voicemeeter', 'ndis', 'aux'
                    ]
                    return any(t in n for t in virtual_terms)

                def score_device(name: str) -> int:
                    # Higher score means more preferred
                    n = name.lower()
                    score = 0
                    if any(k in n for k in ['headset', 'earphone', 'headphones']):
                        score += 100
                    if 'usb' in n:
                        score += 80
                    if any(k in n for k in ['mic', 'microphone', 'array']):
                        score += 60
                    if any(k in n for k in ['realtek', 'intel', 'high definition audio']):
                        score += 20
                    return score

                candidates = [
                    (idx, name, score_device(name))
                    for idx, name in enumerate(mic_list)
                    if not is_virtual(name)
                ]

                if candidates:
                    # Prefer highest score, fall back to first non-virtual
                    best = max(candidates, key=lambda x: x[2])
                    chosen_index = best[0]
                    chosen_name = best[1]
                    self.microphone = sr.Microphone(device_index=chosen_index)
                    print(f"[DEBUG] Using microphone: {chosen_name} (index {chosen_index})")
                else:
                    # As a fallback, use default constructor
                    self.microphone = sr.Microphone()
                    print("[DEBUG] No non-virtual mics detected; using default microphone")
            except Exception as e:
                print(f"[DEBUG] Microphone selection error: {e}")
                self.microphone = sr.Microphone()
            
            # Ultra-sensitive settings for better speech capture
            self.recognizer.energy_threshold = 100  # Very low threshold for maximum sensitivity
            self.recognizer.dynamic_energy_threshold = True  # Automatically adjust based on environment
            self.recognizer.pause_threshold = 1.0  # Longer pause to capture complete sentences
            self.recognizer.non_speaking_duration = 0.8  # Longer non-speaking duration for natural speech
            self.recognizer.phrase_threshold = 0.05  # Very low phrase threshold for better detection
            
            # Adjust for ambient noise with longer duration for better calibration
            try:
                with self.microphone as source:
                    print(f"[DEBUG] Adjusting for ambient noise...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=3)
                    print(f"[DEBUG] Energy threshold set to: {self.recognizer.energy_threshold}")
                    print(f"[DEBUG] Microphone initialized successfully")
                    
                    # Test microphone access
                    print(f"[DEBUG] Testing microphone access...")
                    test_audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=1)
                    print(f"[DEBUG] Microphone access test successful")
                    
            except Exception as e:
                print(f"[DEBUG] Ambient noise adjustment error: {e}")
                # Continue with default settings
            
            self.listening_status.emit("Listening... Speak your question clearly!")
            # Update microphone status to show it's active
            if hasattr(self, 'mic_status'):
                self.mic_status.setText("🎤 Microphone: Active 🎯")
                self.mic_status.setStyleSheet("color:#4CAF50; font-size:12px; font-weight:600;")
            
            # Provide feedback about current sensitivity
            print(f"[DEBUG] Microphone initialized with energy threshold: {self.recognizer.energy_threshold}")
            print(f"[DEBUG] Pause threshold: {self.recognizer.pause_threshold}s")
            print(f"[DEBUG] Non-speaking duration: {self.recognizer.non_speaking_duration}s")
            
            while self.running:
                try:
                    with self.microphone as source:
                        print("[DEBUG] Listening for speech...")
                        self.listening_status.emit("Listening... Speak now!")
                        
                        # Ultra-lenient settings to capture complete speech
                        audio = self.recognizer.listen(
                            source, 
                            timeout=5,  # Longer timeout to capture complete sentences
                            phrase_time_limit=20,  # Increased phrase limit for natural questions
                            snowboy_configuration=None  # Disable wake word detection
                        )
                    
                    if not self.running:
                        break
                        
                    self.listening_status.emit("Processing your speech...")
                    print("[DEBUG] Processing audio...")
                    
                    # Use Google's speech recognition with better language model
                    try:
                        text = self.recognizer.recognize_google(
                            audio, 
                            language=self.language,
                            show_all=False  # Get only the best result
                        )
                        print(f"[DEBUG] Google recognition successful: '{text}'")
                    except sr.RequestError as e:
                        print(f"[DEBUG] Google recognition failed: {e}")
                        # Fallback to Sphinx if Google fails
                        try:
                            text = self.recognizer.recognize_sphinx(audio, language=self.language)
                            print(f"[DEBUG] Sphinx fallback successful: '{text}'")
                        except Exception as sphinx_error:
                            print(f"[DEBUG] Sphinx fallback failed: {sphinx_error}")
                            text = ""
                    
                    if text and len(text.strip()) > 0:
                        print(f"[DEBUG] Recognized: '{text}'")
                        
                        # Check if speech was cut off and adjust sensitivity
                        if len(text.strip()) < 10:  # Very short text might indicate cutoff
                            print("[DEBUG] Short text detected, increasing sensitivity...")
                            self.recognizer.energy_threshold = max(50, self.recognizer.energy_threshold - 50)
                            print(f"[DEBUG] Adjusted energy threshold to: {self.recognizer.energy_threshold}")
                        
                        # Accept ALL speech - no filtering
                        is_question = True  # Accept everything the user says
                        
                        if is_question:
                            print(f"[DEBUG] Question detected: '{text}'")
                            self.recognized.emit(text.strip())
                            self.listening_status.emit("Question received!")
                        else:
                            print(f"[DEBUG] Not a question, ignoring: '{text}'")
                            self.listening_status.emit("Please ask a complete question...")
                    else:
                        print("[DEBUG] No text recognized")
                        self.listening_status.emit("Listening...")
                        
                except sr.WaitTimeoutError:
                    # No speech detected within timeout
                    if self.running:
                        self.listening_status.emit("Listening... (no speech detected)")
                    continue
                except sr.UnknownValueError:
                    # Speech was unintelligible
                    print("[DEBUG] Speech was unintelligible")
                    self.listening_status.emit("Please speak clearly...")
                    continue
                except sr.RequestError as e:
                    # API request failed
                    print(f"[DEBUG] API request failed: {e}")
                    self.listening_status.emit(f"Speech recognition service error: {e}")
                    # Don't break, just continue listening
                    continue
                except Exception as e:
                    print(f"[DEBUG] Speech recognition error: {e}")
                    self.listening_status.emit(f"Speech recognition error: {e}")
                    # Don't break, just continue listening
                    continue
                    
        except Exception as e:
            self.error.emit(f"Failed to initialize speech recognition: {e}")

    def stop(self):
        self.running = False


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
            r = requests.post(f"{BACKEND_URL}/login", json={"email": em, "password": pw}, timeout=12)
            j = r.json()
            if j.get("success"):
                # fetch credits
                gc = requests.post(f"{BACKEND_URL}/get_credits", json={"email": em, "password": pw}, timeout=12).json()
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
            r = requests.post(f"{BACKEND_URL}/signup", json={"email": em, "password": pw}, timeout=12)
            j = r.json()
            if j.get("success"):
                QMessageBox.information(self, "Signup", "Account created! Please log in.")
            else:
                self.status.setText(j.get("message", "Signup failed."))
        except Exception as e:
            self.status.setText(f"Error: {e}")


class MainView(QWidget):
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

        self.listener = None  # WhisperThread
        self._drag_pos = None

        self.setStyleSheet(glass())
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

        self.credit_label = QLabel(f"Credits: {self.credits}")
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

        tips = QLabel(
            "🎤 Voice: Click to listen | 📋 Smart: Alt+Shift+S | 📄 Upload: Alt+Shift+R\n"
            "🖱️ Drag: Click anywhere to move | 🔄 Double-click to resize | ⌨️ Hide/Show: Alt+Shift+H\n"
            "💡 Smart Mode: Uses resume context for personalized answers, falls back to general advice\n"
            "🗣️ Speak anything - all speech is accepted and sent to AI!\n"
            "🔊 Speak clearly and at normal volume - system is now ultra-sensitive!"
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
                cursor: se-resize;
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
        print("[DEBUG] Hide hotkey triggered!")
        # Toggle between hide and show
        if self.isVisible():
            print("[DEBUG] Hiding window...")
            self.hide()
            # Store position before hiding for restoration
            self._stored_pos = self.pos()
            self.listen_status.setText("Window hidden. Press Alt+Shift+H to show.")
        else:
            print("[DEBUG] Showing window...")
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
            requests.post(f"{BACKEND_URL}/logout", timeout=5)
        except Exception:
            pass
        # delete session file
        try:
            os.remove(os.path.expanduser("~/.live_insights_session.json"))
        except Exception:
            pass
        self.request_logout.emit()

    def _install_hotkeys(self):
        # Alt+Shift+S -> Smart mode toggle
        sc_s = QShortcut(QKeySequence("Alt+Shift+S"), self)
        sc_s.activated.connect(self._toggle_smart)

        # Alt+Shift+R -> upload resume
        sc_r = QShortcut(QKeySequence("Alt+Shift+R"), self)
        sc_r.activated.connect(self._upload_resume)

        # Alt+Shift+C -> clear answers
        sc_c = QShortcut(QKeySequence("Alt+Shift+C"), self)
        sc_c.activated.connect(self._clear_answers)

    # (Hide hotkey now only registered globally in MainWindow)

        # Alt+Shift+Q -> quit
        sc_q = QShortcut(QKeySequence("Alt+Shift+Q"), self)
        sc_q.activated.connect(QApplication.quit)

        # Start listening protection
        sc_l = QShortcut(QKeySequence("Alt+Shift+L"), self)
        sc_l.activated.connect(self._toggle_listening)
        
        # Test hotkey to verify system is working
        sc_test = QShortcut(QKeySequence("Alt+Shift+T"), self)
        sc_test.activated.connect(self._test_hotkey)
    
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
                    
                print(f"[DEBUG] Resume uploaded successfully: {filename}")
                print(f"[DEBUG] Resume preview: {resume_preview[:200]}...")
            else:
                self.resume_status.setText("❌ Could not read resume content")
                self.resume_status.setStyleSheet("color:#f44336; font-weight:600;")
                
        except Exception as e:
            self.resume_status.setText(f"❌ Error processing resume: {str(e)}")
            self.resume_status.setStyleSheet("color:#f44336; font-weight:600;")
            print(f"[DEBUG] Resume processing error: {e}")

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
            print(f"[DEBUG] Error reading resume preview: {e}")
            return None
    
    def _clear_answers(self):
        self.answers = []
        self.answers_box.clear()
    
    def _test_hotkey(self):
        """Test method to verify hotkeys are working"""
        print("[DEBUG] Test hotkey Alt+Shift+T pressed!")
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
            self.listen_status.setText("Initializing microphone...")
            self.mic_status.setText("🎤 Microphone: Initializing...")
            self.mic_status.setStyleSheet("color:#FFA500; font-size:12px; font-weight:600;")
            
            # Create and start speech recognition thread
            try:
                self.listener = SpeechRecognitionThread(language="en-US", parent=self)
                self.listener.recognized.connect(self._on_speech)
                self.listener.error.connect(self._on_listen_error)
                self.listener.listening_status.connect(self._on_listening_status)
                self.listener.start()
                print("[DEBUG] Speech recognition thread started")
            except Exception as e:
                print(f"[DEBUG] Failed to start speech recognition: {e}")
                self.listen_status.setText(f"Failed to start: {str(e)}")
                self.mic_status.setText("🎤 Microphone: Error ❌")
                self.mic_status.setStyleSheet("color:#f44336; font-size:12px; font-weight:600;")
                self.listening = False
                self.btn_listen.setText("🎤 Start Listening")
                self.btn_listen.setStyleSheet(button_primary())

    def _on_listen_error(self, msg):
        print(f"[DEBUG] Speech recognition error: {msg}")
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
        print(f"[DEBUG] Speech recognized: '{text}'")  # Debug output
        
        # Accept ALL speech - no filtering or validation
        if not text or len(text.strip()) < 1:  # Only check if text exists
            print("[DEBUG] No text recognized, ignoring")
            return
        
        print(f"[DEBUG] Accepting all speech: '{text}'")
        
        # Add the question to the list
        self.questions.insert(0, text.strip())
        self._render_questions()
        
        # Clear answers - thinking will be shown by _ask_ai
        self.answers_box.clear()
        
        # Force UI update
        QApplication.processEvents()
        
        # Send to AI
        self._ask_ai(text.strip())

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

    def _conversation_history(self):
        # Interleave as in React (sent separately there, but we'll mimic order)
        hist = []
        # Build from oldest to newest based on what we have stored
        # Our local lists hold newest at index 0 because we insert(0,...).
        q_rev = list(reversed(self.questions))
        a_rev = list(reversed(self.answers))
        
        # Create conversation history in chronological order
        for i in range(max(len(q_rev), len(a_rev))):
            if i < len(q_rev):
                hist.append({"role": "user", "content": q_rev[i]})
            if i < len(a_rev):
                hist.append({"role": "assistant", "content": a_rev[i]})
        
        return hist

    def _ask_ai(self, question):
        # mirrors askAI in React
        print(f"[DEBUG] Sending question to AI: '{question}'")
        if self.credits <= 0:
            self.ai_response = "❌ No credits left. Please purchase more credits."
            self._render_answers()
            self._render_ai_response()
            return
            
        # Show thinking indicator
        self.ai_response = "🤔 Thinking..."
        self._render_ai_response()
        QApplication.processEvents()  # Update UI immediately
        
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
                
                self.listen_status.setText("🤖 Sending to AI (Smart Mode - Using Resume Context)...")
                r = requests.post(f"{BACKEND_URL}/ask", files=files, data=data, timeout=90)
                j = r.json()
                print(f"[DEBUG] Full backend response (Smart Mode): {j}")
                ans = j.get("answer") or "No response from AI."
                print(f"[DEBUG] Received AI response (Smart Mode): '{ans[:100]}...'")
                
                # Check if answer was blocked due to template detection
                if "[Error: The answer was blocked" in ans:
                    self.answers = [f"❌ {ans}"]
                    self.listen_status.setText("Answer blocked - please rephrase your question")
                elif "Could not extract any text" in ans:
                    self.answers = [f"❌ {ans}"]
                    self.smart_mode = False
                    self.smart_label.setText("Smart mode: OFF")
                    self.smart_label.setStyleSheet("color: #aaa; font-size:14px;")
                    self.resume_status.setText("❌ Resume text extraction failed")
                    self.resume_status.setStyleSheet("color:#f44336; font-weight:600;")
                else:
                    # Success - answer based on resume context
                    self.answers = [ans]
                    self.listen_status.setText("✅ Resume-based answer received!")
                    
                self.ai_response = ""
                self._render_answers()
                self._deduct_credit()
            else:
                # Global mode
                self.listen_status.setText("🌐 Sending to AI (Global Mode - General Interview Advice)...")
                r = requests.post(f"{BACKEND_URL}/ask",
                                  json={
                                      "question": question,
                                      "email": self.email,
                                      "resume": "",
                                      "mode": "global",
                                      "history": self._conversation_history()
                                  }, timeout=60)
                j = r.json()
                print(f"[DEBUG] Full backend response (Global): {j}")
                ans = j.get("answer") or "No response from AI."
                print(f"[DEBUG] Received AI response (Global): '{ans[:100]}...'")
                
                # Check if answer was blocked due to template detection
                if "[Error: The answer was blocked" in ans:
                    self.answers = [f"❌ {ans}"]
                    self.listen_status.setText("Answer blocked - please rephrase your question")
                else:
                    self.answers = [ans]
                    self.listen_status.setText("✅ General interview advice received!")
                    
                self.ai_response = ""
                self._render_answers()
                self._deduct_credit()
                
            self.listen_status.setText("Response received!")
            
        except requests.exceptions.Timeout:
            self.answers = ["⏰ Request timed out. Please try again."]
            self.ai_response = ""
            self._render_answers()
            self.listen_status.setText("Timeout error")
        except requests.exceptions.ConnectionError:
            self.answers = ["🔌 Connection error. Please check if the backend server is running."]
            self.ai_response = ""
            self._render_answers()
            self.listen_status.setText("Connection error")
        except Exception as e:
            self.answers = [f"❌ Error: {str(e)}"]
            self.ai_response = ""
            self._render_answers()
            self.listen_status.setText("Error occurred")

    def _deduct_credit(self):
        # mirrors React deductCredit()
        try:
            r = requests.post(f"{BACKEND_URL}/use_credit",
                              json={"email": self.email, "password": self.password},
                              timeout=12)
            j = r.json()
            if j.get("success") and isinstance(j.get("credits"), int):
                self.credits = j["credits"]
                self.credit_label.setText(f"Credits: {self.credits}")
            else:
                # fallback to get_credits
                gc = requests.post(f"{BACKEND_URL}/get_credits",
                                   json={"email": self.email, "password": self.password},
                                   timeout=12).json()
                self.credits = gc.get("credits", 0)
                self.credit_label.setText(f"Credits: {self.credits}")
        except Exception:
            try:
                gc = requests.post(f"{BACKEND_URL}/get_credits",
                                   json={"email": self.email, "password": self.password},
                                   timeout=12).json()
                self.credits = gc.get("credits", 0)
                self.credit_label.setText(f"Credits: {self.credits}")
            except Exception:
                self.credit_label.setText("Credits: Error")
                pass




class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live insights - PySide")
        # Frameless but allows free movement and resizing
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
        """Install global hotkey for hide/unhide that works even when window is hidden"""
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
