#!/usr/bin/env python3
"""
Local web UI for audible_to_goodreads.py.

Runs entirely on your machine (127.0.0.1) and never touches your Audible
or Goodreads credentials directly:
  - Audible login happens in its own real terminal window running
    `audible quickstart` (interactive, 2FA-capable) -- this app only
    launches that window, it never sees your password.
  - Goodreads import happens on goodreads.com in your browser -- this app
    only opens the page and hands you a CSV to upload yourself.

Run it with:
    python app.py

The CLI (audible_to_goodreads.py) still works standalone and is what this
UI calls under the hood.
"""

import csv
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file

import audible_to_goodreads as core

BASE_DIR = Path(__file__).resolve().parent
LIBRARY_JSON = BASE_DIR / "library.json"
FULL_CSV = BASE_DIR / "goodreads_import.csv"
TEST_CSV = BASE_DIR / "test_import.csv"
GOODREADS_IMPORT_URL = "https://www.goodreads.com/review/import"
TEST_ROWS = 5
PORT = 5151

app = Flask(__name__)

# Single-user, single-job in-memory state. Good enough for a local tool
# with one browser tab talking to it.
convert_state = {
    "status": "idle",  # idle | running | done | error
    "done": 0,
    "total": 0,
    "current_title": "",
    "matched": 0,
    "shelves": {},
    "error": "",
}
convert_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def audible_cli_installed():
    try:
        subprocess.run(
            ["audible", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def audible_profile_connected():
    try:
        result = subprocess.run(
            ["audible", "manage", "profile", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    return ".json" in result.stdout


def csv_stats(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    matched = sum(1 for r in rows if r.get("ISBN") or r.get("ISBN13"))
    shelves = {}
    for r in rows:
        shelf = r.get("Exclusive Shelf", "unknown")
        shelves[shelf] = shelves.get(shelf, 0) + 1
    return {"total": len(rows), "matched": matched, "shelves": shelves}


@app.route("/api/status")
def api_status():
    library_count = None
    if LIBRARY_JSON.exists():
        try:
            library_count = len(core.load_library(str(LIBRARY_JSON)))
        except Exception:
            library_count = None

    return jsonify(
        {
            "cli_installed": audible_cli_installed(),
            "audible_connected": audible_profile_connected(),
            "library_exported": LIBRARY_JSON.exists(),
            "library_count": library_count,
            "csv_ready": FULL_CSV.exists(),
            "csv_stats": csv_stats(FULL_CSV),
        }
    )


# ---------------------------------------------------------------------------
# Step 1: connect Audible account (interactive, own terminal window)
# ---------------------------------------------------------------------------

@app.route("/api/connect", methods=["POST"])
def api_connect():
    if not audible_cli_installed():
        return jsonify({"ok": False, "error": "audible-cli is not installed."}), 400

    try:
        if sys.platform == "win32":
            subprocess.Popen(
                'start "Audible Login" cmd /k audible quickstart',
                shell=True,
                cwd=str(BASE_DIR),
            )
        else:
            # Best-effort for non-Windows: most terminals support this pattern.
            subprocess.Popen(
                ["x-terminal-emulator", "-e", "audible quickstart"],
                cwd=str(BASE_DIR),
            )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Step 2: export the library (non-interactive once connected)
# ---------------------------------------------------------------------------

@app.route("/api/export", methods=["POST"])
def api_export():
    if not audible_profile_connected():
        return jsonify({"ok": False, "error": "No connected Audible profile yet."}), 400

    try:
        result = subprocess.run(
            ["audible", "library", "export", "-f", "json", "-o", str(LIBRARY_JSON)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Export timed out after 180s."}), 500

    if result.returncode != 0:
        return jsonify({"ok": False, "error": result.stderr.strip() or result.stdout.strip()}), 500

    try:
        count = len(core.load_library(str(LIBRARY_JSON)))
    except Exception as e:
        return jsonify({"ok": False, "error": f"Export ran but output couldn't be read: {e}"}), 500

    return jsonify({"ok": True, "count": count})


# ---------------------------------------------------------------------------
# Step 3: convert to Goodreads CSV (background thread, polled progress)
# ---------------------------------------------------------------------------

def run_conversion(do_lookup):
    with convert_lock:
        convert_state.update(
            status="running", done=0, total=0, current_title="", matched=0, shelves={}, error=""
        )

    def on_progress(idx, total, title):
        with convert_lock:
            convert_state["done"] = idx
            convert_state["total"] = total
            convert_state["current_title"] = title

    try:
        library = core.load_library(str(LIBRARY_JSON))
        with convert_lock:
            convert_state["total"] = len(library)

        rows = core.convert(library, do_lookup=do_lookup, delay=0.5, progress_callback=on_progress)
        core.write_csv(rows, str(FULL_CSV))
        core.write_csv(rows[:TEST_ROWS], str(TEST_CSV))

        stats = csv_stats(FULL_CSV)
        with convert_lock:
            convert_state.update(status="done", matched=stats["matched"], shelves=stats["shelves"])
    except Exception as e:
        with convert_lock:
            convert_state.update(status="error", error=str(e))


@app.route("/api/convert", methods=["POST"])
def api_convert():
    if not LIBRARY_JSON.exists():
        return jsonify({"ok": False, "error": "No library.json yet. Export first."}), 400
    with convert_lock:
        if convert_state["status"] == "running":
            return jsonify({"ok": False, "error": "A conversion is already running."}), 409

    do_lookup = (request.get_json(silent=True) or {}).get("isbn_lookup", True)

    thread = threading.Thread(target=run_conversion, args=(do_lookup,), daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.route("/api/convert/progress")
def api_convert_progress():
    with convert_lock:
        return jsonify(dict(convert_state))


# ---------------------------------------------------------------------------
# Downloads + handoff to Goodreads
# ---------------------------------------------------------------------------

@app.route("/download/test")
def download_test():
    if not TEST_CSV.exists():
        return "test_import.csv not generated yet", 404
    return send_file(TEST_CSV, as_attachment=True, download_name="test_import.csv")


@app.route("/download/full")
def download_full():
    if not FULL_CSV.exists():
        return "goodreads_import.csv not generated yet", 404
    return send_file(FULL_CSV, as_attachment=True, download_name="goodreads_import.csv")


@app.route("/api/goodreads-url")
def api_goodreads_url():
    return jsonify({"url": GOODREADS_IMPORT_URL})


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Starting Audible -> Goodreads UI at {url}")
    app.run(host="127.0.0.1", port=PORT, debug=False)
