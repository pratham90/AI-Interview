
from flask import Flask, render_template, request, jsonify, session
import requests
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change this to a secure value

BACKEND_URL = os.getenv("BACKEND_URL", "https://ai-assis-54jg.onrender.com")

@app.route('/')
def index():
    return render_template('index.html', logged_in=session.get("user"), user=session.get("user"))

@app.route('/api/login', methods=['POST'])
def login():
    resp = requests.post(f"{BACKEND_URL}/login", json=request.json)
    data = resp.json()
    if resp.status_code == 200 and data.get("success"):
        session["user"] = request.json.get("email")
    return jsonify(data), resp.status_code

@app.route('/api/signup', methods=['POST'])
def signup():
    resp = requests.post(f"{BACKEND_URL}/signup", json=request.json)
    data = resp.json()
    if resp.status_code == 200 and data.get("success"):
        session["user"] = request.json.get("email")
    return jsonify(data), resp.status_code

@app.route('/api/ask', methods=['POST'])
def ask():
    payload = request.json
    if session.get("user"):
        payload["email"] = session.get("user")
    resp = requests.post(f"{BACKEND_URL}/ask", json=payload)
    return jsonify(resp.json()), resp.status_code

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop("user", None)
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True)