from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import os
import time
import csv

import os
import sys

# Ensure project root is on sys.path so this file can be run directly
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import main_selenium as ms

# Point Flask to the project's top-level `templates` and `static` folders
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
        run_state["message"] = "Launching browser..."
        results = ms.scrape_keyword(keyword, headless=headless, limit_records=limit_records)
        run_state["last_count"] = len(results or [])
        run_state["message"] = f"Finished. Parsed {run_state['last_count']} records."
    except Exception as e:
        run_state["message"] = f"Error: {e}"
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
        limit = int(data.get("limit_records", ms.MAX_RECORDS))
    except Exception:
        limit = ms.MAX_RECORDS

    headless = bool(data.get("headless", False))
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
    path = os.path.join(os.getcwd(), "data")
    filename = os.path.basename(ms.OUTPUT_CSV)
    full = os.path.join(path, filename)
    if not os.path.exists(full):
        return jsonify({"status":"error","message":"No output file"}), 404
    rows = []
    try:
        with open(full, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for r in reader:
                # csv.DictReader may produce a None key for extra columns
                # (when a row has more values than headers). Clean such rows
                # so they contain only string keys and values before JSONifying.
                cleaned = {}
                extra_parts = []
                for k, v in r.items():
                    if k is None:
                        if v is not None:
                            extra_parts.append(str(v))
                        continue
                    # normalize None values to empty string
                    cleaned[str(k)] = "" if v is None else v
                if extra_parts:
                    cleaned["_extra"] = " | ".join(extra_parts)
                rows.append(cleaned)
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 500
    return jsonify({"status":"ok","rows":rows})


@app.route("/download")
def download():
    path = os.path.join(os.getcwd(), "data")
    filename = os.path.basename(ms.OUTPUT_CSV)
    if not os.path.exists(ms.OUTPUT_CSV):
        return jsonify({"status": "error", "message": "No output file yet"}), 404
    return send_from_directory(directory=path, path=filename, as_attachment=True)


if __name__ == "__main__":
    # Run dev server
    app.run(host="127.0.0.1", port=5000, debug=True)
