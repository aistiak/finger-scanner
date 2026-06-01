"""Regenerate lib.py from ../main.py after parent app changes. Not used at runtime."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT_MAIN = ROOT.parent / "main.py"
LIB_OUT = ROOT / "lib.py"

HEADER_TEXT = '''"""RTMS Biometric desktop application library."""
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import base64
import io
import sqlite3
from datetime import datetime
import threading
import time
import multiprocessing
import sys
import os

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path():
    return os.path.join(app_dir(), "app_settings.json")


def db_path():
    return os.path.join(app_dir(), "fingerprints-1.db")


def init_db():
    conn = sqlite3.connect(db_path())
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fingerprints (
        id INTEGER PRIMARY KEY,
        finger_id INTEGER UNIQUE,
        template BLOB
    )
    """)
    conn.commit()
    conn.close()


def list_fingers():
    init_db()
    conn = sqlite3.connect(db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT finger_id, template FROM fingerprints ORDER BY finger_id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def _registration_worker_process(progress_queue, result_queue):
    try:
        from pyzkfp import ZKFP2
        progress_queue.put("Initializing fingerprint device...")
        zkfp2 = ZKFP2()
        zkfp2.Init()
        progress_queue.put("Opening device...")
        zkfp2.OpenDevice(0)
        progress_queue.put("Device connected successfully")
        templates = []
        for i in range(3):
            progress_queue.put(f"Place finger {i + 1}/3 - Waiting for finger on scanner...")
            while True:
                capture = zkfp2.AcquireFingerprint()
                if capture:
                    templates.append(capture[0])
                    progress_queue.put(f"Finger {i + 1}/3 captured. Please lift your finger.")
                    break
        progress_queue.put("Processing fingerprint template...")
        reg_temp, _ = zkfp2.DBMerge(*templates)
        template_b64 = base64.b64encode(bytes(reg_temp)).decode("utf-8")
        try:
            zkfp2.Terminate()
        except Exception:
            pass
        result_queue.put(("ok", template_b64))
    except Exception as e:
        result_queue.put(("error", str(e)))


def _match_worker_process(progress_queue, result_queue, stored_template_b64):
    try:
        from pyzkfp import ZKFP2
        stored_template = base64.b64decode(stored_template_b64)
        progress_queue.put("Initializing fingerprint device...")
        zkfp2 = ZKFP2()
        zkfp2.Init()
        progress_queue.put("Opening device...")
        zkfp2.OpenDevice(0)
        progress_queue.put("Device connected successfully")
        templates = []
        for i in range(3):
            progress_queue.put(f"Place finger {i + 1}/3 - Waiting for finger on scanner...")
            while True:
                capture = zkfp2.AcquireFingerprint()
                if capture:
                    templates.append(capture[0])
                    progress_queue.put(f"Finger {i + 1}/3 captured. Please lift your finger.")
                    break
        progress_queue.put("Processing captured fingerprint...")
        live_template, _ = zkfp2.DBMerge(*templates)
        progress_queue.put("Comparing fingerprints...")
        match_result = zkfp2.DBMatch(stored_template, live_template)
        try:
            zkfp2.Terminate()
        except Exception:
            pass
        result_queue.put(("ok", match_result > 0))
    except Exception as e:
        result_queue.put(("error", str(e)))


'''

RUN_APP = '''

def run_app():
    root = tk.Tk()
    root.geometry("420x320")
    root.configure(bg="#f0f0f0")

    def show_login():
        for w in root.winfo_children():
            w.destroy()
        root.geometry("420x320")
        LoginScreen(root, on_success=on_login_success)

    def on_login_success(token, user_info):
        for w in root.winfo_children():
            w.destroy()
        root.geometry("900x700")
        FingerprintApp(root, auth_token=token, user_info=user_info, on_logout=show_login)

    show_login()
    root.mainloop()
'''


def main():
    text = PARENT_MAIN.read_text(encoding="utf-8")
    start = text.find("# Beman loophole")
    end = text.find("\ndef main():")
    if start < 0 or end < 0:
        raise SystemExit("Could not slice parent main.py")
    body = text[start:end]
    body = body.replace('settings_file = "app_settings.json"', "settings_file = settings_path()")
    body = body.replace("settings_file = 'app_settings.json'", "settings_file = settings_path()")
    LIB_OUT.write_text(HEADER_TEXT + body + RUN_APP, encoding="utf-8")
    print(f"Wrote {LIB_OUT} ({LIB_OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
