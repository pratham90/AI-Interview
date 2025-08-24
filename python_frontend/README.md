# AI Desktop Assistant - Enhanced Frontend

This is an enhanced desktop application for your AI Interview Assistant with advanced voice recognition capabilities and seamless backend integration.

## 🚀 Features

### Voice Recognition
- **Real-time Speech-to-Text**: Uses OpenAI Whisper for accurate voice recognition
- **Adjustable Sensitivity**: Control voice detection sensitivity with a slider
- **Voice Activity Indicator**: Visual feedback when voice is detected
- **Noise Reduction**: Filters out background noise and silence
- **Continuous Listening**: Automatically processes speech in real-time

### Smart Mode
- **Resume Integration**: Upload your resume for personalized interview responses
- **Contextual Answers**: AI provides answers based on your resume content
- **Fallback to Global**: Automatically switches to general advice if resume doesn't cover the question
- **Multiple File Formats**: Supports PDF, TXT, DOC, DOCX files

### User Interface
- **Modern Glassmorphism Design**: Beautiful dark theme with transparency effects
- **Frameless Window**: Draggable, always-on-top interface
- **Hotkey Support**: Keyboard shortcuts for all major functions
- **Session Management**: Automatic login and session persistence
- **Credit System**: Track and display remaining AI credits

## 📋 Requirements

### System Requirements
- Python 3.8 or higher
- Windows 10/11 (tested on Windows)
- Microphone for voice input
- At least 4GB RAM (8GB recommended for Whisper)

### Python Dependencies
```
PySide6
requests
numpy
sounddevice
openai-whisper
pyaudio
```

## 🛠️ Installation

1. **Install Dependencies**:
   ```bash
   cd python_frontend
   pip install -r requirements.txt
   ```

2. **Start Backend Server**:
   ```bash
   cd ../backend
   python api_server.py
   ```

3. **Launch Desktop App**:
   ```bash
   cd ../python_frontend
   python launch_desktop.py
   ```

## 🎯 Usage

### Getting Started
1. **Login/Signup**: Create an account or log in with existing credentials
2. **Upload Resume** (Optional): Click "Upload Resume" or press `Alt+Shift+R`
3. **Enable Smart Mode**: Toggle with `Alt+Shift+S` (requires resume)
4. **Start Listening**: Click "🎤 Start Listening" or press `Alt+Shift+L`

### Voice Commands
- **Speak Clearly**: Enunciate your words for better recognition
- **Pause Between Questions**: Give the AI time to process
- **Adjust Sensitivity**: Use the slider to match your environment
- **Stop Listening**: Click "⏹️ Stop Listening" when done

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| `Alt+Shift+L` | Start/Stop Listening |
| `Alt+Shift+S` | Toggle Smart Mode |
| `Alt+Shift+R` | Upload Resume |
| `Alt+Shift+C` | Clear Answers |
| `Alt+Shift+H` | Hide Window |
| `Alt+Shift+U` | Unhide Window |
| `Alt+Shift+Q` | Quit Application |

### Smart Mode Features
- **Personalized Responses**: AI uses your resume for contextual answers
- **Automatic Fallback**: Switches to general advice if resume doesn't help
- **File Size Limit**: Maximum 10MB for resume files
- **Supported Formats**: PDF, TXT, DOC, DOCX

## 🔧 Configuration

### Voice Sensitivity
- **Low (1-3)**: Less sensitive, good for quiet environments
- **Medium (4-7)**: Balanced sensitivity (recommended)
- **High (8-10)**: Very sensitive, good for noisy environments

### Backend Connection
- **Default URL**: `http://127.0.0.1:5000`
- **Timeout**: 60-90 seconds for AI responses
- **Auto-reconnect**: Automatic retry on connection errors

## 🧪 Testing

Run the test script to verify everything is working:

```bash
python test_backend.py
```

This will test:
- Backend connection
- User authentication
- AI response generation
- File upload functionality

## 🐛 Troubleshooting

### Voice Recognition Issues
1. **Check Microphone**: Ensure microphone is working and not muted
2. **Adjust Sensitivity**: Use the slider to find the right level
3. **Environment**: Reduce background noise
4. **Speak Clearly**: Enunciate and speak at normal volume

### Connection Issues
1. **Backend Running**: Ensure `api_server.py` is running
2. **Port 5000**: Check if port 5000 is available
3. **Firewall**: Allow Python through Windows Firewall
4. **Test Connection**: Run `test_backend.py`

### Performance Issues
1. **Whisper Model**: Use "tiny" model for faster processing
2. **Close Other Apps**: Free up system resources
3. **Update Dependencies**: Ensure all packages are up to date

## 📁 File Structure

```
python_frontend/
├── ai_desktop.py          # Main desktop application
├── launch_desktop.py      # Launcher with dependency checks
├── test_backend.py        # Backend connection tester
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── ffmpeg/               # FFmpeg binaries (if needed)
```

## 🔄 Backend Integration

The desktop app connects to your backend API with these endpoints:

- `POST /login` - User authentication
- `POST /signup` - User registration
- `POST /ask` - AI question processing
- `POST /use_credit` - Credit management
- `POST /get_credits` - Credit balance

## 🎨 UI Features

- **Glassmorphism Design**: Modern transparent interface
- **Dark Theme**: Easy on the eyes
- **Responsive Layout**: Adapts to window size
- **Visual Feedback**: Status indicators and progress updates
- **Drag & Drop**: Move window by dragging the header

## 🔒 Security

- **Session Persistence**: Secure local storage of login credentials
- **Automatic Logout**: Session expires after 7 days
- **Secure Communication**: HTTPS-ready backend communication
- **No Data Storage**: Voice data is processed locally and not stored

## 📈 Performance Tips

1. **Use Tiny Whisper Model**: Faster processing for real-time recognition
2. **Close Unused Apps**: Free up CPU and memory
3. **Good Microphone**: Invest in a quality microphone for better accuracy
4. **Stable Internet**: Ensure good connection for AI responses

## 🤝 Contributing

To enhance the desktop app:

1. **Voice Recognition**: Modify `WhisperThread` class
2. **UI Design**: Update styles in the style functions
3. **Backend Integration**: Modify API calls in `_ask_ai` method
4. **New Features**: Add methods to `MainView` class

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Run `test_backend.py` to verify backend connectivity
3. Check the console output for error messages
4. Ensure all dependencies are properly installed

---

**Happy Interviewing! 🎯**
