#!/usr/bin/env python3
"""
Launcher script for the AI Desktop Assistant
"""

import sys
import os
import subprocess
import importlib.util

def check_dependency(module_name, package_name=None):
    """Check if a Python module is available"""
    if package_name is None:
        package_name = module_name
    
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        print(f"❌ Missing dependency: {package_name}")
        return False
    else:
        print(f"✅ {package_name} is available")
        return True

def check_backend():
    """Check if backend is running"""
    try:
        import requests
        response = requests.get("http://127.0.0.1:5000/", timeout=3)
        print("✅ Backend server is running")
        return True
    except:
        print("❌ Backend server is not running")
        print("   Please start the backend first:")
        print("   cd backend && python api_server.py")
        return False

def main():
    print("🚀 AI Desktop Assistant Launcher")
    print("=" * 40)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    else:
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} is available")
    
    # Check required dependencies
    print("\n📦 Checking dependencies:")
    dependencies = [
        ("PySide6", "PySide6"),
        ("requests", "requests"),
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("whisper", "openai-whisper"),
        ("wave", "wave"),  # Built-in
        ("queue", "queue"),  # Built-in
        ("tempfile", "tempfile"),  # Built-in
        ("threading", "threading"),  # Built-in
    ]
    
    missing_deps = []
    for module, package in dependencies:
        if not check_dependency(module, package):
            missing_deps.append(package)
    
    if missing_deps:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        print("Please install them with:")
        print(f"pip install {' '.join(missing_deps)}")
        sys.exit(1)
    
    # Check backend
    print("\n🔗 Checking backend connection:")
    if not check_backend():
        sys.exit(1)
    
    # Launch the desktop app
    print("\n🎯 Starting AI Desktop Assistant...")
    try:
        from ai_desktop import MainWindow
        from PySide6.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        app.setApplicationName("AI Desktop Assistant")
        w = MainWindow()
        w.show()
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ Failed to start desktop app: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
