from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import os
import csv
import sys

# Bulletproof path resolving
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == "src":
    BASE_DIR = os.path.abspath(os.path.join(current_dir, ".."))
else:
    BASE_DIR = current_dir

# Add root folder to paths
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# CRITICAL FIX FOR RENDER: Tell Gunicorn to also look inside the 'src' folder!
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import main_selenium as ms

TEMPLATES_PATH = os.path.join(BASE_DIR, "templates")
STATIC_PATH = os.path.join(BASE_DIR, "static")
app = Flask(__name__, static_folder=STATIC_PATH, template_folder=TEMPLATES_PATH)

run_state = {
    "running": False,
    "message": "Idle",
    "last_count": 0
}

def _run_scraper_thread(keyword, headless, limit_records, user_data_dir, profile_dir):
    run_state["running"] = True
    run_state["message"] = "Starting..."
    try:
        if user_data_dir:
            ms.USER_DATA_DIR = user_data_dir
        if profile_dir:
            ms.PROFILE_DIR = profile_dir
        
        run_state["message"] = "Launching browser & loading cookies..."
        print(f"\n[INFO] Starting scraper thread for keyword: '{keyword}'", flush=True)
        
        results = ms.scrape_keyword(keyword, headless=headless, limit_records=limit_records)
        
        run_state["last_count"] = len(results or [])
        run_state["message"] = f"Finished. Parsed {run_state['last_count']} records."
        print(f"[INFO] Thread finished successfully. Found {run_state['last_count']} records.", flush=True)
    except Exception as e:
        run_state["message"] = f"Error: {e}"
        print(f"[ERROR] Scraper thread crashed: {e}", flush=True)
    finally:
        run_state["running"] = False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    if run_state["running"]:
        return jsonify({"status": "already-running"}), 409

    data = request.json or {}
    keyword = data.get("keyword", "").strip()
    if not keyword:
        return jsonify({"status": "error", "message": "Keyword required"}), 400

    try:
        limit = int(data.get("limit_records") or ms.MAX_RECORDS)
    except Exception:
        limit = ms.MAX_RECORDS

    headless = bool(data.get("headless", False))
    
    # Auto-force Headless when deployed to Render
    if os.environ.get("RENDER") or os.path.exists("/.dockerenv"):
        headless = True

    user_data_dir = data.get("user_data_dir") or ms.USER_DATA_DIR
    profile_dir = data.get("profile_dir") or ms.PROFILE_DIR

    t = threading.Thread(target=_run_scraper_thread, args=(keyword, headless, limit, user_data_dir, profile_dir), daemon=True)
    t.start()

    return jsonify({"status": "started"})

@app.route("/status")
def status():
    return jsonify(run_state)

@app.route("/results")
def results():
    full = os.path.join(BASE_DIR, "data", "output.csv")
    if not os.path.exists(full):
        return jsonify({"status":"error","message":"No output file found. Check the terminal for errors."}), 404
    
    rows = []
    try:
        with open(full, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for r in reader:
                cleaned = {}
                extra_parts = []
                for k, v in r.items():
                    if k is None:
                        if v is not None:
                            extra_parts.append(str(v))
                        continue
                    cleaned[str(k)] = "" if v is None else v
                if extra_parts:
                    cleaned["_extra"] = " | ".join(extra_parts)
                rows.append(cleaned)
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 500
    
    return jsonify({"status":"ok","rows":rows})

@app.route("/download")
def download():
    data_dir = os.path.join(BASE_DIR, "data")
    if not os.path.exists(os.path.join(data_dir, "output.csv")):
        return jsonify({"status": "error", "message": "No output file yet"}), 404
    return send_from_directory(directory=data_dir, path="output.csv", as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)