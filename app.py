import os
import subprocess
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import json
from pathlib import Path

app = Flask(__name__)
app.secret_key = "DPXHOSTSECRET"

UPLOAD_FOLDER = "bots"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ACCESS_CODE = "DPX1432"

DB_FILE = "processes.json"

def read_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def write_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def start_bot_docker(bot_name):
    bot_dir = Path(UPLOAD_FOLDER) / bot_name
    py_files = list(bot_dir.glob("*.py"))
    if not py_files:
        return False, "No .py file found!"
    entry = py_files[0].name

    container_name = f"bot_{bot_name}"

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--restart", "unless-stopped",
        "-v", f"{str(bot_dir.resolve())}:/app",
        "-w", "/app",
        "python:3.11-slim",
        "/bin/bash", "-c",
        f"pip install -r requirements.txt --no-cache-dir || true; python {entry}"
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        db = read_db()
        db[bot_name] = {"container": out, "status": "running"}
        write_db(db)
        return True, f"Started bot in container {out[:12]}"
    except subprocess.CalledProcessError as e:
        return False, e.output.decode()

def stop_bot_docker(bot_name):
    try:
        subprocess.call(["docker", "stop", f"bot_{bot_name}"])
        subprocess.call(["docker", "rm", f"bot_{bot_name}"])
        db = read_db()
        if bot_name in db:
            db[bot_name]["status"] = "stopped"
            write_db(db)
        return True, "Bot stopped successfully!"
    except Exception as e:
        return False, str(e)

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        code = request.form.get("access_code")
        if code == ACCESS_CODE:
            session["auth"] = True
            return redirect("/panel")
        else:
            flash("❌ Wrong access code!")
    return render_template("login.html")

@app.route("/panel")
def panel():
    if not session.get("auth"):
        return redirect("/")
    bots = os.listdir(UPLOAD_FOLDER)
    db = read_db()
    return render_template("index.html", bots=bots, db=db)

@app.route("/upload", methods=["POST"])
def upload_bot():
    if not session.get("auth"):
        return redirect("/")
    file = request.files["file"]
    if not file:
        flash("No file selected!")
        return redirect("/panel")

    bot_name = os.path.splitext(secure_filename(file.filename))[0]
    bot_path = Path(UPLOAD_FOLDER) / bot_name
    os.makedirs(bot_path, exist_ok=True)

    save_path = bot_path / secure_filename(file.filename)
    file.save(save_path)
    flash(f"✅ Bot uploaded: {bot_name}")
    return redirect("/panel")

@app.route("/start/<bot>")
def start(bot):
    success, msg = start_bot_docker(bot)
    flash(("✅ " if success else "❌ ") + msg)
    return redirect("/panel")

@app.route("/stop/<bot>")
def stop(bot):
    success, msg = stop_bot_docker(bot)
    flash(("🛑 " if success else "❌ ") + msg)
    return redirect("/panel")

@app.route("/delete/<bot>")
def delete(bot):
    bot_dir = Path(UPLOAD_FOLDER) / bot
    stop_bot_docker(bot)
    subprocess.call(["rm", "-rf", str(bot_dir)])
    db = read_db()
    if bot in db:
        del db[bot]
        write_db(db)
    flash("🗑️ Bot deleted!")
    return redirect("/panel")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
