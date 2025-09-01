# Cross-Platform Setup Guide for Live Insights AI Desktop App

This guide ensures the app works on Windows, macOS, and Linux systems.

## 🖥️ Platform Detection

The app automatically detects your platform and optimizes:
- **Windows**: Conservative settings for stability
- **macOS**: Balanced settings for performance  
- **Linux**: Aggressive settings for maximum speed

## 📦 Installation by Platform

### Windows
```bash
# Install Python 3.8+ from python.org
# Install Visual C++ Build Tools if PyAudio fails
pip install -r requirements_cross_platform.txt
```

### macOS
```bash
# Install Homebrew first
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install portaudio
brew install portaudio

# Install Python packages
pip install -r requirements_cross_platform.txt
```

### Linux (Ubuntu/Debian)
```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-pyaudio

# Install Python packages
pip install -r requirements_cross_platform.txt
```

### Linux (CentOS/RHEL/Fedora)
```bash
# For CentOS/RHEL
sudo yum install -y portaudio-devel python3-pyaudio

# For Fedora
sudo dnf install -y portaudio-devel python3-pyaudio

# Install Python packages
pip install -r requirements_cross_platform.txt
```

### Linux (Arch)
```bash
# Install system dependencies
sudo pacman -S --noconfirm portaudio python-pyaudio

# Install Python packages
pip install -r requirements_cross_platform.txt
```

## 🔑 Platform-Specific Hotkeys

| Platform | Smart Mode | Upload Resume | Hide/Show | Clear | Quit |
|----------|------------|---------------|-----------|-------|------|
| Windows  | Alt+Shift+S | Alt+Shift+R | Alt+Shift+H | Alt+Shift+C | Alt+Shift+Q |
| macOS    | Cmd+Shift+S | Cmd+Shift+R | Cmd+Shift+H | Cmd+Shift+C | Cmd+Shift+Q |
| Linux    | Alt+Shift+S | Alt+Shift+R | Alt+Shift+H | Alt+Shift+C | Alt+Shift+Q |

## 💳 New Credit System

- **1 credit deducted for every 2 genuine answers**
- No credit deduction for blocked/failed answers
- Progress indicator shows remaining answers needed
- More cost-effective for users

## 🚀 Performance Optimizations

### Windows
- Conservative energy threshold (150)
- Longer pause detection (0.4s)
- Stable timeout settings (3s)

### macOS  
- Balanced energy threshold (120)
- Medium pause detection (0.3s)
- Optimized timeout settings (2s)

### Linux
- Aggressive energy threshold (80)
- Fast pause detection (0.2s)
- Minimal timeouts (1s)

## 🔧 Troubleshooting

### Audio Issues
- **Windows**: Install Visual C++ Build Tools
- **macOS**: Ensure Homebrew and portaudio are installed
- **Linux**: Install system audio packages (portaudio19-dev)

### Speech Recognition
- Check microphone permissions
- Ensure internet connection for Google recognition
- Try different microphone devices

### GUI Issues
- **Windows**: Update graphics drivers
- **macOS**: Check accessibility permissions
- **Linux**: Install Qt dependencies

## 📱 Running the App

```bash
# Navigate to the python_frontend directory
cd python_frontend

# Run the app
python ai_desktop.py
```

## 🌟 Features

- **Cross-platform compatibility** with automatic optimization
- **Smart credit system** (1 credit per 2 answers)
- **Platform-specific hotkeys** for native feel
- **Optimized speech recognition** for each OS
- **Automatic microphone selection** with device scoring
- **Resume-based AI responses** with fallback to general advice

## 📞 Support

If you encounter issues:
1. Check platform-specific requirements above
2. Ensure all dependencies are installed
3. Verify microphone permissions
4. Check internet connection for AI responses

The app automatically adapts to your platform for the best experience!
