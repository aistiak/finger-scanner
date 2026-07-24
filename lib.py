"""RTMS Biometric desktop application library."""
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
import socket
import sys
import os
import traceback

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from fingerprint_workers import (
    decode_finger_image_bytes,
    _registration_worker_process,
    _capture_worker_process,
    _match_worker_process,
    _sequential_match_worker_process,
)
from barcode_print import (
    print_barcode_async,
    resolve_printable_serial,
)


def app_dir():
    """Directory for settings/DB: exe folder when frozen, else this package folder."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path():
    return os.path.join(app_dir(), "app_settings.json")


def db_path():
    return os.path.join(app_dir(), "fingerprints-1.db")


def logs_path():
    return os.path.join(app_dir(), "logs.txt")


_log_lock = threading.Lock()


def _write_log(level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}\n"
    try:
        with _log_lock:
            with open(logs_path(), "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def log_info(message):
    _write_log("INFO", str(message))


def log_error(message):
    _write_log("ERROR", str(message))


def log_exception(message, exc=None):
    if exc is not None:
        detail = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).strip()
        _write_log("ERROR", f"{message}\n{detail}")
        return
    exc_info = sys.exc_info()
    if exc_info[0] is not None:
        detail = "".join(traceback.format_exception(*exc_info)).strip()
        _write_log("ERROR", f"{message}\n{detail}")
    else:
        _write_log("ERROR", str(message))


def install_global_exception_logger():
    def _hook(exc_type, exc_value, exc_tb):
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).strip()
        _write_log("ERROR", f"Uncaught exception\n{detail}")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def normalize_server_url(url):
    return (url or "https://rtmsbd.com").strip().rstrip("/")


def api_request_headers(auth_token=None):
    """Headers for Laravel API calls. Accept: application/json avoids HTML error pages."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    return headers


APP_VERSION = "1.2.0"

FINGER_SCAN_HISTORY_ACTIONS = (
    "login",
    "logout",
    "add",
    "scan",
    "match",
    "search",
    "delete",
    "update",
)


def resolve_device_name():
    """Workstation label for history payloads."""
    try:
        name = (socket.gethostname() or "").strip()
        return name or None
    except Exception:
        return None


def finger_scan_history_url(server_url):
    return f"{normalize_server_url(server_url)}/api/v1/finger-scan/history"


def _history_optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _history_optional_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _history_optional_str(value, max_len=None):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_len is not None and len(text) > max_len:
        return text[:max_len]
    return text


def subject_fields_from_user_data(user_data):
    """Map passport / identify payload fields into history subject keys."""
    if not isinstance(user_data, dict):
        return {}
    fingerprint = user_data.get("fingerprint") if isinstance(user_data.get("fingerprint"), dict) else {}
    branch = user_data.get("branch") if isinstance(user_data.get("branch"), dict) else {}
    fields = {
        "passport_number": _history_optional_str(
            user_data.get("passport_number") or user_data.get("passport")
        ),
        "registration_id": _history_optional_str(resolve_registration_id(user_data)),
        "subject_name": _history_optional_str(
            user_data.get("full_name") or user_data.get("name") or user_data.get("subject_name")
        ),
        "service_request_id": _history_optional_int(
            user_data.get("service_request_id") or user_data.get("service_id")
        ),
        "fingerprint_id": _history_optional_int(
            fingerprint.get("id")
            or fingerprint.get("fingerprint_id")
            or user_data.get("fingerprint_id")
        ),
    }
    branch_name = _history_optional_str(branch.get("name") or user_data.get("branch_name"))
    if branch_name:
        fields["branch_name"] = branch_name
    return {k: v for k, v in fields.items() if v is not None}


def build_finger_scan_history_payload(
    action,
    status,
    message=None,
    user_info=None,
    settings=None,
    subject=None,
    **extras,
):
    """Build POST /api/v1/finger-scan/history body. Only action+status are required."""
    action = (action or "").strip().lower()
    status = (status or "").strip().lower()
    if action not in FINGER_SCAN_HISTORY_ACTIONS:
        raise ValueError(f"Invalid history action: {action}")
    if status not in ("success", "failed"):
        raise ValueError(f"Invalid history status: {status}")

    user_info = user_info or {}
    settings = settings or {}
    payload = {
        "action": action,
        "status": status,
        "action_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "device_name": resolve_device_name(),
    }

    message = _history_optional_str(message, max_len=500)
    if message:
        payload["message"] = message

    user_id = _history_optional_int(user_info.get("id") or user_info.get("user_id"))
    if user_id is not None:
        payload["user_id"] = user_id
    user_name = _history_optional_str(user_info.get("name") or user_info.get("user_name"))
    if user_name:
        payload["user_name"] = user_name
    user_email = _history_optional_str(user_info.get("email") or user_info.get("user_email"))
    if user_email:
        payload["user_email"] = user_email
    user_role = _history_optional_str(user_info.get("role") or user_info.get("user_role"))
    if user_role:
        payload["user_role"] = user_role

    branch_id = resolve_branch_id(user_info, settings)
    if branch_id is not None:
        payload["branch_id"] = branch_id
    branch_name = _history_optional_str(
        user_info.get("branch_name")
        or (settings.get("branch_name") if isinstance(settings, dict) else None)
    )
    if branch_name:
        payload["branch_name"] = branch_name

    if isinstance(subject, dict):
        payload.update(subject_fields_from_user_data(subject))

    allowed_extras = (
        "passport_number",
        "registration_id",
        "service_request_id",
        "subject_name",
        "fingerprint_id",
        "matched_passport_number",
        "matched_fingerprint_id",
        "match_score",
        "ip_address",
        "meta",
        "branch_name",
    )
    for key, value in extras.items():
        if key not in allowed_extras or value is None:
            continue
        if key in ("service_request_id", "fingerprint_id", "matched_fingerprint_id"):
            value = _history_optional_int(value)
        elif key == "match_score":
            value = _history_optional_float(value)
        elif key == "meta":
            if not isinstance(value, dict):
                continue
        else:
            value = _history_optional_str(value, max_len=500 if key == "message" else None)
        if value is not None:
            payload[key] = value

    return {k: v for k, v in payload.items() if v is not None}


def post_finger_scan_history(server_url, payload, background=True):
    """
    POST one history row. Fire-and-forget by default so UI is never blocked.
    Errors are logged locally; they never raise to the caller.
    """
    def _send():
        try:
            url = finger_scan_history_url(server_url)
            response = requests.post(
                url,
                json=payload,
                headers=api_request_headers(),
                timeout=5,
            )
            if response.status_code not in (200, 201):
                log_error(
                    f"Finger history API HTTP {response.status_code}: "
                    f"{(response.text or '')[:300]}"
                )
            else:
                log_info(
                    f"Finger history stored: action={payload.get('action')} "
                    f"status={payload.get('status')}"
                )
        except Exception as e:
            log_exception("Finger history API request failed", e)

    if background:
        threading.Thread(target=_send, daemon=True).start()
        return
    _send()


def parse_api_response(response):
    """Return (data_dict or None, error_message). error_message set when body is not JSON."""
    content_type = (response.headers.get("Content-Type") or "").lower()
    text = (response.text or "").strip()
    if not text:
        return None, f"Empty response from server (HTTP {response.status_code})."
    if "json" not in content_type and not (text.startswith("{") or text.startswith("[")):
        return None, (
            f"Server returned non-JSON (HTTP {response.status_code}). "
            "Use https:// in Settings and ensure the API is online."
        )
    try:
        return response.json(), None
    except json.JSONDecodeError:
        return None, (
            f"Invalid JSON from server (HTTP {response.status_code}). "
            "Use https:// in Settings and try again."
        )


def extract_api_error_message(data, response):
    if not isinstance(data, dict):
        return response.text or f"HTTP {response.status_code}"
    if data.get("message"):
        msg = str(data["message"])
        if "Unknown column 'token'" in msg:
            return (
                "Server error: login token cannot be saved (missing token column in database). "
                "Contact the RTMS administrator to fix the users table."
            )
        return msg
    errors = data.get("errors")
    if isinstance(errors, dict):
        parts = []
        for field, msgs in errors.items():
            if isinstance(msgs, list):
                parts.append(f"{field}: {', '.join(str(m) for m in msgs)}")
            else:
                parts.append(f"{field}: {msgs}")
        if parts:
            return "; ".join(parts)
    return str(data.get("error") or response.text or f"HTTP {response.status_code}")


def normalize_branch_id(value):
    """Return branch_id suitable for query params, or None if missing/invalid."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("id") or value.get("branch_id")
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def extract_login_user_info(data):
    """Map login API success payload to app user_info (supports nested or flat shapes)."""
    user_data = data.get("data")
    if not isinstance(user_data, dict):
        user_data = data.get("user") if isinstance(data.get("user"), dict) else {}
    token = user_data.get("token") or data.get("token") or data.get("access_token")
    branch_raw = user_data.get("branch_id")
    branch_name = None
    if isinstance(user_data.get("branch"), dict):
        branch = user_data["branch"]
        if branch_raw is None:
            branch_raw = branch.get("id")
        branch_name = branch.get("name")
    if branch_raw is None:
        branch_raw = data.get("branch_id")
    if not branch_name:
        branch_name = user_data.get("branch_name") or data.get("branch_name")
    user_id = user_data.get("id") or user_data.get("user_id") or data.get("id")
    return {
        "id": _history_optional_int(user_id),
        "name": user_data.get("name") or data.get("name") or "",
        "email": user_data.get("email") or data.get("email") or "",
        "phone_number": user_data.get("phone_number") or data.get("phone_number") or "",
        "role": (user_data.get("role") or data.get("role") or "").strip().lower(),
        "token": token,
        "token_expires_at": user_data.get("token_expires_at") or data.get("token_expires_at"),
        "branch_id": normalize_branch_id(branch_raw),
        "branch_name": _history_optional_str(branch_name),
    }


def resolve_registration_id(user_data):
    """Read printable serial from API payload (registration_id / daily_serial_no)."""
    return resolve_printable_serial(user_data)


def enrich_user_data_with_registration_id(user_data, fingerprint_lookup_url, auth_token=None):
    """Load registration_id and finger_image from GET /api/v1/finger/passport when missing."""
    if not isinstance(user_data, dict):
        return user_data
    fingerprint_info = user_data.get("fingerprint") or {}
    needs_registration_id = resolve_registration_id(user_data) is None
    needs_finger_image = not (
        (isinstance(user_data.get("finger_image"), str) and user_data.get("finger_image").strip())
        or (isinstance(fingerprint_info.get("finger_image"), str) and fingerprint_info.get("finger_image").strip())
    )
    if not needs_registration_id and not needs_finger_image:
        return user_data
    passport_number = user_data.get("passport_number")
    if not passport_number:
        return user_data
    try:
        url = f"{fingerprint_lookup_url.rstrip('/')}/{passport_number}"
        response = requests.get(url, headers=api_request_headers(auth_token), timeout=10)
        if response.status_code != 200:
            log_error(
                f"Fingerprint lookup failed HTTP {response.status_code} for {passport_number}"
            )
            return user_data
        payload, parse_err = parse_api_response(response)
        if parse_err or not payload.get("success"):
            if parse_err:
                log_error(f"Fingerprint lookup failed for {passport_number}: {parse_err}")
            return user_data
        finger_data = payload.get("data") or {}
        enriched = dict(user_data)
        changed = False
        registration_id = resolve_registration_id(finger_data)
        if needs_registration_id and registration_id is not None:
            enriched["registration_id"] = registration_id
            changed = True
            log_info(f"Loaded registration_id={registration_id} for passport {passport_number}")
        finger_image = finger_data.get("finger_image")
        if needs_finger_image and isinstance(finger_image, str) and finger_image.strip():
            fp = dict(enriched.get("fingerprint") or {})
            fp["finger_image"] = finger_image.strip()
            enriched["fingerprint"] = fp
            changed = True
            log_info(f"Loaded finger_image for passport {passport_number}")
        return enriched if changed else user_data
    except Exception as e:
        log_error(f"Could not enrich fingerprint data for {passport_number}: {e}")
        return user_data


def resolve_branch_id(user_info=None, settings=None):
    """Read branch_id from session user_info, remembered user, or saved settings."""
    settings = settings or {}
    user_info = user_info or {}
    for source in (user_info, settings.get("remembered_user") or {}, settings):
        branch_id = normalize_branch_id(source.get("branch_id"))
        if branch_id is not None:
            return branch_id
    return None


def persist_branch_id(branch_id):
    """Save branch_id to app_settings.json (top-level and remembered_user when present)."""
    branch_id = normalize_branch_id(branch_id)
    if branch_id is None:
        return
    try:
        settings = {}
        if os.path.exists(settings_path()):
            with open(settings_path(), "r", encoding="utf-8") as f:
                settings = json.load(f)
        settings["branch_id"] = branch_id
        remembered = settings.get("remembered_user")
        if isinstance(remembered, dict):
            remembered["branch_id"] = branch_id
            settings["remembered_user"] = remembered
        settings["last_updated"] = datetime.now().isoformat()
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        log_error(f"Could not save branch_id: {e}")


def is_auth_ok_token_save_failed(data, response):
    """True when password was accepted but server failed saving token to DB."""
    if response.status_code != 500 or not isinstance(data, dict):
        return False
    return "Unknown column 'token'" in str(data.get("message", ""))


def load_remembered_user():
    try:
        if os.path.exists(settings_path()):
            with open(settings_path(), "r", encoding="utf-8") as f:
                return json.load(f).get("remembered_user") or {}
    except Exception:
        pass
    return {}


def load_saved_session():
    """
    Return (token, user_info) if Remember me session exists and can restore login.
    Otherwise return None.
    """
    remembered = load_remembered_user()
    if not remembered.get("remember_me"):
        return None
    email = (remembered.get("email") or "").strip()
    if not email and not remembered.get("_beman_loophole"):
        return None
    user_info = {
        "id": _history_optional_int(remembered.get("id")),
        "name": remembered.get("name") or (email.split("@")[0] if email else "User"),
        "email": email,
        "phone_number": remembered.get("phone_number") or "",
        "role": (remembered.get("role") or "user").strip().lower(),
        "branch_id": normalize_branch_id(remembered.get("branch_id")),
        "branch_name": _history_optional_str(remembered.get("branch_name")),
        "token": remembered.get("token"),
        "token_expires_at": remembered.get("token_expires_at"),
    }
    if remembered.get("_beman_loophole"):
        user_info["_beman_loophole"] = True
        user_info["role"] = "super_admin"
    if remembered.get("_login_without_token"):
        user_info["_login_without_token"] = True
    token = user_info.get("token")
    # Beman / no-token sessions are valid without a token; API sessions need one.
    if not token and not user_info.get("_beman_loophole") and not user_info.get("_login_without_token"):
        return None
    return token, user_info


def remember_user_info(user_info, remember_me=False):
    """Persist user details locally. When remember_me is True, also store the auth token."""
    try:
        settings = {}
        if os.path.exists(settings_path()):
            with open(settings_path(), "r", encoding="utf-8") as f:
                settings = json.load(f)
        branch_id = normalize_branch_id(user_info.get("branch_id"))
        payload = {
            "id": _history_optional_int(user_info.get("id")),
            "name": user_info.get("name") or "",
            "email": user_info.get("email") or "",
            "phone_number": user_info.get("phone_number") or "",
            "role": user_info.get("role") or "",
            "branch_id": branch_id,
            "branch_name": _history_optional_str(user_info.get("branch_name")),
            "remember_me": bool(remember_me),
        }
        if remember_me:
            payload["token"] = user_info.get("token")
            payload["token_expires_at"] = user_info.get("token_expires_at")
            if user_info.get("_beman_loophole"):
                payload["_beman_loophole"] = True
            if user_info.get("_login_without_token"):
                payload["_login_without_token"] = True
        settings["remembered_user"] = payload
        if branch_id is not None:
            settings["branch_id"] = branch_id
        settings["last_updated"] = datetime.now().isoformat()
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        log_error(f"Could not save remembered user: {e}")


def clear_remembered_user_settings():
    """Remove remembered user and branch_id from app_settings.json (e.g. on logout)."""
    try:
        path = settings_path()
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        changed = False
        if "remembered_user" in settings:
            del settings["remembered_user"]
            changed = True
        if "branch_id" in settings:
            del settings["branch_id"]
            changed = True
        if not changed:
            return
        settings["last_updated"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        log_error(f"Could not clear remembered user settings: {e}")


def user_info_without_token(email, remembered=None):
    """Build session user_info when API auth succeeded but no token is available."""
    remembered = remembered or {}
    settings = _load_settings_for_login()
    email = (email or "").strip()
    if remembered.get("email", "").lower() == email.lower():
        return {
            "id": _history_optional_int(remembered.get("id")),
            "name": remembered.get("name") or email.split("@")[0],
            "email": email,
            "phone_number": remembered.get("phone_number") or "",
            "role": (remembered.get("role") or "user").strip().lower(),
            "branch_id": resolve_branch_id(remembered, settings),
            "branch_name": _history_optional_str(remembered.get("branch_name")),
            "token": None,
            "token_expires_at": None,
            "_login_without_token": True,
        }
    return {
        "name": email.split("@")[0] if email else "User",
        "email": email,
        "phone_number": "",
        "role": "user",
        "branch_id": resolve_branch_id({}, settings),
        "token": None,
        "token_expires_at": None,
        "_login_without_token": True,
    }


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


# Page size when listing templates from GET /api/v1/finger/identify
IDENTIFY_PAGE_LIMIT = 50

# ZKTeco DBMatch: real matches are typically 60–100+; low scores are noise.
MATCH_SCORE_THRESHOLD = 60
MATCH_SCORE_EARLY_EXIT = 85


# Beman loophole: treat as super user (full access)
BEMAN_USERNAME = "beman"
BEMAN_PASSWORD = "beman"
SUPER_ADMIN_ROLE = "super_admin"
FULL_ACCESS_ROLES = (SUPER_ADMIN_ROLE,)  # super_admin and beman get full access


def _load_settings_for_login():
    """Load settings from JSON (used before main app exists)."""
    settings_file = settings_path()
    default = {"server_url": "https://rtmsbd.com", "last_updated": datetime.now().isoformat()}
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                return json.load(f)
        with open(settings_file, 'w') as f:
            json.dump(default, f, indent=2)
        return default
    except Exception:
        return default


class LoginScreen:
    """Login window shown when app starts. On success calls on_success(token, user_info)."""
    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success
        self.frame = ttk.Frame(root, padding=40)
        self.frame.pack(fill='both', expand=True)
        self.settings = _load_settings_for_login()
        self._build_ui()

    def _build_ui(self):
        self.root.title("RTMS Biometric system – Login")
        self.root.geometry("420x360")
        self.root.configure(bg='#f0f0f0')
        ttk.Style().configure('TLabel', background='#f0f0f0')
        title = ttk.Label(self.frame, text="Login", font=('Arial', 18, 'bold'))
        title.pack(pady=(0, 24))
        # Email
        ttk.Label(self.frame, text="Email").pack(anchor='w')
        self.email_var = tk.StringVar()
        email_entry = ttk.Entry(self.frame, textvariable=self.email_var, width=35, font=('Arial', 11))
        email_entry.pack(fill='x', pady=(2, 12))
        remembered = load_remembered_user()
        if remembered.get("email"):
            self.email_var.set(remembered["email"])
        email_entry.focus()
        # Password
        ttk.Label(self.frame, text="Password").pack(anchor='w')
        self.password_var = tk.StringVar()
        pass_entry = ttk.Entry(self.frame, textvariable=self.password_var, width=35, show='•', font=('Arial', 11))
        pass_entry.pack(fill='x', pady=(2, 12))
        pass_entry.bind('<Return>', lambda e: self._do_login())
        # Remember me
        self.remember_me_var = tk.BooleanVar(value=bool(remembered.get("remember_me")))
        ttk.Checkbutton(
            self.frame,
            text="Remember me",
            variable=self.remember_me_var,
        ).pack(anchor='w', pady=(0, 16))
        # Buttons
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill='x', pady=(0, 8))
        self.login_btn = ttk.Button(btn_frame, text="Login", command=self._do_login)
        self.login_btn.pack(side='left', padx=(0, 10))
        self.status_label = ttk.Label(self.frame, text="", foreground='#c00')
        self.status_label.pack(anchor='w', pady=(4, 0))

    def _persist_login_session(self, user_info):
        """Save or clear session based on Remember me checkbox."""
        if self.remember_me_var.get():
            remember_user_info(user_info, remember_me=True)
            persist_branch_id(user_info.get("branch_id"))
        else:
            clear_remembered_user_settings()

    def _record_history(self, action, status, message=None, user_info=None, **extras):
        """Fire-and-forget finger action history (login screen)."""
        try:
            payload = build_finger_scan_history_payload(
                action,
                status,
                message=message,
                user_info=user_info,
                settings=self.settings,
                **extras,
            )
            post_finger_scan_history(self.settings.get("server_url"), payload)
        except Exception as e:
            log_exception("Could not queue finger history event", e)

    def _do_login(self):
        email = (self.email_var.get() or "").strip()
        password = self.password_var.get() or ""
        if not email:
            self.status_label.configure(text="Please enter email.")
            return
        if not password:
            self.status_label.configure(text="Please enter password.")
            return
        # Beman loophole: username beman + password beman = super user, no API call
        if email.lower() == BEMAN_USERNAME and password == BEMAN_PASSWORD:
            log_info("Login: local super user (beman)")
            user_info = {
                "name": "Beman (Super User)",
                "email": BEMAN_USERNAME,
                "phone_number": "",
                "role": SUPER_ADMIN_ROLE,
                "token": None,
                "token_expires_at": None,
                "_beman_loophole": True,
            }
            self._persist_login_session(user_info)
            self._record_history(
                "login",
                "success",
                message="Login successful (local super user)",
                user_info=user_info,
            )
            self.on_success(None, user_info)
            return
        self.login_btn.configure(state='disabled')
        self.status_label.configure(text="Signing in...")
        log_info(f"Login attempt: {email}")
        thread = threading.Thread(target=self._login_thread, args=(email, password))
        thread.daemon = True
        thread.start()

    def _login_thread(self, email, password):
        try:
            server_url = normalize_server_url(self.settings.get("server_url"))
            url = f"{server_url}/api/v1/login"
            body = {"email": email, "password": password}
            headers = api_request_headers()
            response = requests.post(url, json=body, headers=headers, timeout=15)
            data, _ = parse_api_response(response)
            if (
                response.status_code == 422
                and isinstance(data, dict)
                and data.get("errors")
            ):
                response = requests.post(
                    url,
                    data=body,
                    headers={"Accept": "application/json"},
                    timeout=15,
                )
            self.root.after(0, self._handle_login_response, response, email)
        except requests.exceptions.RequestException as e:
            self.root.after(0, self._handle_login_error, str(e), email)

    def _handle_login_response(self, response, email):
        self.login_btn.configure(state='normal')
        try:
            data, parse_err = parse_api_response(response)
            if parse_err:
                log_error(f"Login failed: {parse_err} body={response.text[:300]}")
                self.status_label.configure(text=parse_err)
                self._record_history(
                    "login",
                    "failed",
                    message=parse_err,
                    user_info={"email": email},
                )
                return
            if response.status_code == 200 and data.get("success"):
                user_info = extract_login_user_info(data)
                if not user_info.get("email"):
                    user_info["email"] = email
                self._persist_login_session(user_info)
                log_info(
                    f"Login success: {user_info.get('email')} role={user_info.get('role')} "
                    f"branch_id={user_info.get('branch_id')} "
                    f"token={'yes' if user_info.get('token') else 'no'} "
                    f"remember_me={self.remember_me_var.get()}"
                )
                self.status_label.configure(text="")
                self._record_history(
                    "login",
                    "success",
                    message="Login successful",
                    user_info=user_info,
                )
                self.on_success(user_info.get("token"), user_info)
                return
            if is_auth_ok_token_save_failed(data, response):
                user_info = user_info_without_token(email, load_remembered_user())
                self._persist_login_session(user_info)
                log_info(
                    f"Login: valid credentials for {email}, continuing without API token "
                    f"(role={user_info.get('role')})"
                )
                self.status_label.configure(text="")
                self._record_history(
                    "login",
                    "success",
                    message="Login successful (without API token)",
                    user_info=user_info,
                )
                self.on_success(None, user_info)
                return
            msg = extract_api_error_message(data, response)
            log_error(f"Login failed (HTTP {response.status_code}): {msg}")
            self.status_label.configure(text=msg)
            self._record_history(
                "login",
                "failed",
                message=msg,
                user_info={"email": email},
            )
        except Exception as e:
            log_exception("Login response handling failed", e)
            self.status_label.configure(text=str(e))
            self._record_history(
                "login",
                "failed",
                message=str(e),
                user_info={"email": email},
            )

    def _handle_login_error(self, err, email=None):
        self.login_btn.configure(state='normal')
        log_error(f"Login connection error: {err}")
        self.status_label.configure(text=f"Connection error: {err}")
        self._record_history(
            "login",
            "failed",
            message=f"Connection error: {err}",
            user_info={"email": email} if email else None,
        )


FRONTDESK_ROLE = "frontdesk"
PHLEBOTOMIST_ROLE = "phlebotomist"

def _can_register(user_info):
    """True if user can register fingerprint: super_admin, beman loophole, or frontdesk."""
    if not user_info:
        return False
    role = (user_info.get('role') or '').strip().lower()
    if role == SUPER_ADMIN_ROLE:
        return True
    if user_info.get('_beman_loophole'):
        return True
    if role == FRONTDESK_ROLE:
        return True
    return False


def _can_match(user_info):
    """True if user can match fingerprint. Frontdesk cannot match; everyone else can."""
    if not user_info:
        return False
    role = (user_info.get('role') or '').strip().lower()
    return role != FRONTDESK_ROLE


def _can_print_barcode(user_info):
    """True if user can print sample barcodes (phlebotomist only)."""
    if not user_info:
        return False
    role = (user_info.get("role") or "").strip().lower()
    return role == PHLEBOTOMIST_ROLE


class FingerprintApp:
    def __init__(self, root, auth_token=None, user_info=None, on_logout=None):
        self.root = root
        self.auth_token = auth_token
        self.user_info = user_info or {}
        self.on_logout = on_logout
        self.root.title("RTMS Biometric system")
        self.root.geometry("1100x850")
        self.root.minsize(1000, 780)
        self.root.configure(bg='#f0f0f0')
        self.can_register = _can_register(user_info)
        self.can_match = _can_match(user_info)
        self.can_print_barcode = _can_print_barcode(user_info)
        self._last_auto_printed_serial = None
        self.auto_print_var = None  # set after settings load for phlebotomist
        
        # Initialize database
        init_db()
        
        # Configure styles
        self.setup_styles()
        
        # Top bar: logged-in user + Logout
        top_bar = ttk.Frame(root)
        top_bar.pack(fill='x', padx=10, pady=(10, 0))
        role_display = (self.user_info.get('role') or 'user').strip()
        if self.user_info.get('_beman_loophole'):
            role_display = "super user (beman)"
        name_display = self.user_info.get('name') or self.user_info.get('email') or 'User'
        ttk.Label(top_bar, text=f"Logged in as {name_display} ({role_display})", style='Info.TLabel').pack(side='left')
        if self.on_logout:
            ttk.Button(top_bar, text="Logout", command=self._logout).pack(side='right')
        
        # Create main notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Load settings
        self.settings = self.load_settings()
        session_branch_id = resolve_branch_id(self.user_info, self.settings)
        if session_branch_id is not None:
            self.settings["branch_id"] = session_branch_id
            if normalize_branch_id(self.user_info.get("branch_id")) is not None:
                persist_branch_id(session_branch_id)
        
        # API URLs from settings (before tabs; used when enriching user details)
        server_url = normalize_server_url(self.settings.get('server_url'))
        self.api_base_url = server_url + "/api/v1/service-request/passport/"
        self.fingerprint_api_url = server_url + "/api/v1/fingerprint/register"
        self.fingerprint_lookup_url = server_url + "/api/v1/finger/passport"
        self.fingerprint_identify_url = server_url + "/api/v1/finger/identify"
        self.finger_scan_history_url = server_url + "/api/v1/finger-scan/history"
        self.login_url_base = server_url.rstrip('/')  # for logout
        self._registration_is_update = False

        if self.can_print_barcode:
            self.auto_print_var = tk.BooleanVar(
                value=bool(self.settings.get("auto_print_barcode", False))
            )

        # Create tabs: Register/Match by role; Auto Search + Settings for everyone
        if self.can_register:
            self.create_register_tab()
        self.create_auto_search_tab()
        if self.can_match:
            self.create_match_tab()
        self.create_settings_tab()
        log_info(
            f"App started: user={name_display} role={role_display} "
            f"branch_id={resolve_branch_id(self.user_info, self.settings)} server={server_url}"
        )

    def _record_history(self, action, status, message=None, subject=None, **extras):
        """Fire-and-forget finger action history for the logged-in session."""
        try:
            payload = build_finger_scan_history_payload(
                action,
                status,
                message=message,
                user_info=self.user_info,
                settings=self.settings,
                subject=subject,
                **extras,
            )
            server_url = getattr(self, "login_url_base", None) or self.settings.get("server_url")
            post_finger_scan_history(server_url, payload)
        except Exception as e:
            log_exception("Could not queue finger history event", e)

    def _logout(self):
        """Call logout API (if token exists) then return to login screen."""
        if self.on_logout is None:
            return
        token = self.auth_token
        if token:
            def do_logout():
                try:
                    url = f"{self.login_url_base}/api/v1/logout"
                    requests.post(url, json={"token": token}, headers=api_request_headers(), timeout=10)
                except Exception:
                    pass
                self.root.after(0, self._on_logout_done)
            threading.Thread(target=do_logout, daemon=True).start()
        else:
            self._on_logout_done()

    def _on_logout_done(self):
        """Switch back to login screen (clear main app, show login)."""
        self._record_history("logout", "success", message="User logged out")
        clear_remembered_user_settings()
        log_info("User logged out")
        if self.on_logout:
            self.on_logout()
        
    def setup_styles(self):
        """Configure custom styles for the application"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure custom styles
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'), background='#f0f0f0')
        style.configure('Heading.TLabel', font=('Arial', 12, 'bold'), background='#f0f0f0')
        style.configure('Info.TLabel', font=('Arial', 10), background='#f0f0f0')
        style.configure('Success.TLabel', font=('Arial', 10), foreground='#28a745', background='#f0f0f0')
        style.configure('Error.TLabel', font=('Arial', 10), foreground='#dc3545', background='#f0f0f0')
        style.configure('MatchSuccess.TLabel', font=('Arial', 16, 'bold'), foreground='#28a745', background='#f0f0f0')
        style.configure('MatchNoMatch.TLabel', font=('Arial', 16, 'bold'), foreground='#dc3545', background='#f0f0f0')
        
    def create_register_tab(self):
        """Create the registration tab"""
        register_frame = ttk.Frame(self.notebook)
        self.notebook.add(register_frame, text="Register")
        
        # Main container with padding
        main_container = ttk.Frame(register_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_container, text="Fingerprint Registration", style='Title.TLabel')
        title_label.pack(pady=(0, 10))
        
        # Compact top bar: Search + Register side by side
        top_frame = ttk.LabelFrame(main_container, text="Search & Register", padding=10)
        top_frame.pack(fill='x', pady=(0, 10))
        row1 = ttk.Frame(top_frame)
        row1.pack(fill='x')
        ttk.Label(row1, text="Passport Number:", style='Heading.TLabel').pack(side='left', padx=(0, 5))
        self.passport_entry = ttk.Entry(row1, font=('Arial', 12), width=18)
        self.passport_entry.pack(side='left', padx=(0, 8))
        self.search_btn = ttk.Button(row1, text="Search", command=self.search_passport)
        self.search_btn.pack(side='left', padx=(0, 15))
        self.register_fp_btn = ttk.Button(row1, text="Register Fingerprint",
                                         command=self.register_fingerprint, state='disabled')
        self.register_fp_btn.pack(side='left', padx=(0, 8))
        self.cancel_register_btn = ttk.Button(row1, text="Cancel", command=self._cancel_registration)
        self.cancel_register_btn.pack(side='left')
        self.cancel_register_btn.pack_forget()
        self.loading_label = ttk.Label(top_frame, text="", style='Info.TLabel')
        self.loading_label.pack(anchor='w', pady=(6, 0))
        self.register_status_label = ttk.Label(top_frame, text="", style='Info.TLabel')
        self.register_status_label.pack(anchor='w', pady=(2, 0))
        self.registration_cancelled = False
        self._registration_just_cancelled = False
        self.current_user_data = None
        
        # User details section (gets most of the space)
        self.details_frame = ttk.LabelFrame(main_container, text="User Details", padding=15)
        self.details_frame.pack(fill='both', expand=True, pady=(0, 0))
        self.details_frame.pack_forget()
        
    def create_match_tab(self):
        """Create the matching tab"""
        match_frame = ttk.Frame(self.notebook)
        self.notebook.add(match_frame, text="Match")
        
        # Main container with padding
        main_container = ttk.Frame(match_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_container, text="Fingerprint Matching", style='Title.TLabel')
        title_label.pack(pady=(0, 10))
        
        # Compact top bar: Search + Match side by side (same as Register tab)
        top_frame = ttk.LabelFrame(main_container, text="Search & Match", padding=10)
        top_frame.pack(fill='x', pady=(0, 10))
        row1 = ttk.Frame(top_frame)
        row1.pack(fill='x')
        ttk.Label(row1, text="Passport Number:", style='Heading.TLabel').pack(side='left', padx=(0, 5))
        self.match_passport_entry = ttk.Entry(row1, font=('Arial', 12), width=18)
        self.match_passport_entry.pack(side='left', padx=(0, 8))
        self.match_search_btn = ttk.Button(row1, text="Search", command=self.match_search_passport)
        self.match_search_btn.pack(side='left', padx=(0, 15))
        self.match_btn = ttk.Button(row1, text="Match Fingerprint", command=self.match_fingerprint)
        self.match_btn.pack(side='left', padx=(0, 8))
        self.cancel_match_btn = ttk.Button(row1, text="Cancel", command=self._cancel_match)
        self.cancel_match_btn.pack(side='left')
        self.cancel_match_btn.pack_forget()
        if self.can_print_barcode:
            self.match_print_barcode_btn = ttk.Button(
                row1, text="Print Barcode", command=self._print_match_barcode
            )
            self.match_print_barcode_btn.pack(side='left', padx=(15, 0))
            self.match_auto_print_cb = ttk.Checkbutton(
                row1,
                text="Auto Print",
                variable=self.auto_print_var,
                command=self._on_auto_print_toggled,
            )
            self.match_auto_print_cb.pack(side='left', padx=(10, 0))
        self.match_loading_label = ttk.Label(top_frame, text="", style='Info.TLabel')
        self.match_loading_label.pack(anchor='w', pady=(6, 0))
        self.match_result_label = ttk.Label(top_frame, text="", style='Info.TLabel')
        self.match_result_label.pack(anchor='w', pady=(2, 0))
        self.current_match_user_data = None
        self.match_cancelled = False
        self._match_process = None
        
        # User details section (gets most of the space, same as Register)
        self.match_details_frame = ttk.LabelFrame(main_container, text="User Details", padding=15)
        self.match_details_frame.pack(fill='both', expand=True, pady=(0, 0))
        self.match_details_frame.pack_forget()
        
    def create_auto_search_tab(self):
        """Create auto search tab (fingerprint first, then identify via API). Visible to all roles."""
        auto_frame = ttk.Frame(self.notebook)
        self.notebook.add(auto_frame, text="Auto Search")
        
        main_container = ttk.Frame(auto_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        title_label = ttk.Label(main_container, text="Fingerprint Auto Search", style='Title.TLabel')
        title_label.pack(pady=(0, 10))
        
        top_frame = ttk.LabelFrame(main_container, text="Scan & Identify", padding=10)
        top_frame.pack(fill='x', pady=(0, 10))
        row1 = ttk.Frame(top_frame)
        row1.pack(fill='x')
        self.auto_search_btn = ttk.Button(row1, text="Auto Search", command=self.auto_search)
        self.auto_search_btn.pack(side='left', padx=(0, 8))
        self.cancel_auto_search_btn = ttk.Button(row1, text="Cancel", command=self._cancel_auto_search)
        self.cancel_auto_search_btn.pack(side='left')
        self.cancel_auto_search_btn.pack_forget()
        if self.can_print_barcode:
            self.auto_search_print_barcode_btn = ttk.Button(
                row1, text="Print Barcode", command=self._print_auto_search_barcode
            )
            self.auto_search_print_barcode_btn.pack(side='left', padx=(15, 0))
            self.auto_search_auto_print_cb = ttk.Checkbutton(
                row1,
                text="Auto Print",
                variable=self.auto_print_var,
                command=self._on_auto_print_toggled,
            )
            self.auto_search_auto_print_cb.pack(side='left', padx=(10, 0))
        self.auto_search_status_label = ttk.Label(top_frame, text="Place finger on scanner to search by fingerprint.", style='Info.TLabel')
        self.auto_search_status_label.pack(anchor='w', pady=(8, 0))
        
        self.auto_search_cancelled = False
        self._auto_search_process = None
        self.current_auto_search_user_data = None
        
        self.auto_search_details_frame = ttk.LabelFrame(main_container, text="User Details", padding=15)
        self.auto_search_details_frame.pack(fill='both', expand=True, pady=(0, 0))
        self.auto_search_details_frame.pack_forget()
        
    def create_settings_tab(self):
        """Create the settings tab"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")
        
        # Main container with padding
        main_container = ttk.Frame(settings_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_container, text="Application Settings", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Server Configuration Section
        server_frame = ttk.LabelFrame(main_container, text="Server Configuration", padding=15)
        server_frame.pack(fill='x', pady=(0, 20))
        
        # Server URL input
        url_label = ttk.Label(server_frame, text="Server URL:", style='Heading.TLabel')
        url_label.pack(anchor='w', pady=(0, 5))
        
        url_help_label = ttk.Label(server_frame, text="Enter the base server URL (e.g., http://192.168.1.100:4111)", 
                                  style='Info.TLabel')
        url_help_label.pack(anchor='w', pady=(0, 10))
        
        self.server_url_entry = ttk.Entry(server_frame, font=('Arial', 12), width=50)
        self.server_url_entry.pack(fill='x', pady=(0, 10))
        
        # Load current setting
        current_url = self.settings.get('server_url', 'https://rtmsbd.com')
        self.server_url_entry.insert(0, current_url)
        
        # Buttons frame
        buttons_frame = ttk.Frame(server_frame)
        buttons_frame.pack(fill='x', pady=(10, 0))
        
        # Test connection button
        self.test_btn = ttk.Button(buttons_frame, text="Test Connection", command=self.test_connection)
        self.test_btn.pack(side='left', padx=(0, 10))
        
        # Save settings button
        self.save_btn = ttk.Button(buttons_frame, text="Save Settings", command=self.save_settings_ui)
        self.save_btn.pack(side='left')
        
        # Reset to default button
        reset_btn = ttk.Button(buttons_frame, text="Reset to Default", command=self.reset_to_default)
        reset_btn.pack(side='right')
        
        # Status label
        self.settings_status_label = ttk.Label(server_frame, text="", style='Info.TLabel')
        self.settings_status_label.pack(anchor='w', pady=(10, 0))
        
        # Application Info Section
        info_frame = ttk.LabelFrame(main_container, text="Application Information", padding=15)
        info_frame.pack(fill='x', pady=(0, 20))
        
        info_text = """
Fingerprint Registration System v1.0

This application allows you to:
• Search passport information via API
• Register fingerprints linked to passport data
• Match fingerprints against stored templates
• Auto search by fingerprint (no passport number required)
• Configure server settings

Settings are automatically saved to your local machine.
        """
        
        info_label = ttk.Label(info_frame, text=info_text.strip(), style='Info.TLabel', justify='left')
        info_label.pack(anchor='w')
        
        # Database Info Section
        db_frame = ttk.LabelFrame(main_container, text="Database Information", padding=15)
        db_frame.pack(fill='x')
        
        # Database status
        db_status_frame = ttk.Frame(db_frame)
        db_status_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(db_status_frame, text="Database File:", style='Heading.TLabel').pack(side='left')
        ttk.Label(db_status_frame, text="fingerprints-1.db", style='Info.TLabel').pack(side='left', padx=(10, 0))
        
        # Refresh database info button
        refresh_db_btn = ttk.Button(db_frame, text="Refresh Database Info", command=self.refresh_db_info)
        refresh_db_btn.pack(anchor='w', pady=(0, 10))
        
        # Database info display
        self.db_info_label = ttk.Label(db_frame, text="", style='Info.TLabel')
        self.db_info_label.pack(anchor='w')
        
        # Load initial database info
        self.refresh_db_info()
        
    def search_passport(self):
        """Search for passport information via API"""
        passport_number = self.passport_entry.get().strip()
        if not passport_number:
            messagebox.showerror("Error", "Please enter a passport number")
            return
            
        # Disable search button and show loading
        self.search_btn.configure(state='disabled')
        self.loading_label.configure(text="Searching...", style='Info.TLabel')
        log_info(f"Register tab: passport search {passport_number}")
        
        # Run API call in separate thread to prevent UI freezing
        thread = threading.Thread(target=self._api_search_thread, args=(passport_number,))
        thread.daemon = True
        thread.start()
        
    def _api_search_thread(self, passport_number):
        """API search in separate thread"""
        try:
            url = f"{self.api_base_url}{passport_number}"
            response = requests.get(url, headers=api_request_headers(self.auth_token), timeout=10)
            user_data = None
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('success') and isinstance(data.get('data'), dict):
                        user_data = enrich_user_data_with_registration_id(
                            data['data'], self.fingerprint_lookup_url, self.auth_token
                        )
                except json.JSONDecodeError:
                    pass
            
            # Schedule UI update in main thread
            self.root.after(0, self._handle_api_response, response, passport_number, user_data)
            
        except requests.exceptions.RequestException as e:
            log_exception(f"Register tab: passport search failed ({passport_number})", e)
            self.root.after(0, self._handle_api_error, str(e), passport_number)
            
    def _handle_api_response(self, response, passport_number, enriched_user_data=None):
        """Handle API response in main thread"""
        try:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.current_user_data = enriched_user_data if enriched_user_data is not None else data.get('data')
                    self._display_user_details(self.current_user_data)
                    self.loading_label.configure(text="User found successfully!", style='Success.TLabel')
                    log_info(f"Register tab: user found {passport_number}")
                    self._record_history(
                        "search",
                        "success",
                        message="Record found",
                        subject=self.current_user_data,
                        passport_number=passport_number,
                    )
                    
                    # Check fingerprint status and update button accordingly
                    fingerprint_info = self.current_user_data.get('fingerprint', {})
                    is_registered = fingerprint_info.get('registered', False)
                    
                    if is_registered:
                        self.register_fp_btn.configure(text="Re-register Fingerprint", state='normal')
                        self.register_status_label.configure(text="⚠️ User already has fingerprint registered", style='Info.TLabel')
                    else:
                        self.register_fp_btn.configure(text="Register Fingerprint", state='normal')
                        self.register_status_label.configure(text="Ready to register fingerprint", style='Info.TLabel')
                else:
                    self._handle_api_error(data.get('message', 'Unknown error'), passport_number)
            else:
                self._handle_api_error(f"HTTP {response.status_code}: {response.text}", passport_number)
                
        except json.JSONDecodeError:
            self._handle_api_error("Invalid response format", passport_number)
        except Exception as e:
            self._handle_api_error(str(e), passport_number)
        finally:
            self.search_btn.configure(state='normal')
            
    def _handle_api_error(self, error_message, passport_number=None):
        """Handle API errors"""
        log_error(f"Register tab: {error_message}")
        self.loading_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        self.search_btn.configure(state='normal')
        self.details_frame.pack_forget()
        self.register_fp_btn.configure(state='disabled')
        self.current_user_data = None
        self._record_history(
            "search",
            "failed",
            message=error_message,
            passport_number=passport_number,
        )
        
    def _ensure_registration_id(self, user_data):
        """Merge registration_id from finger/passport API when absent on passport payload."""
        if not user_data:
            return user_data
        return enrich_user_data_with_registration_id(
            user_data, self.fingerprint_lookup_url, self.auth_token
        )

    def _display_user_details(self, user_data):
        """Display user details with left (details) and right (photo/emoji) layout"""
        user_data = self._ensure_registration_id(user_data)
        self.current_user_data = user_data
        for widget in self.details_frame.winfo_children():
            widget.destroy()
        self.details_frame.pack(fill='x', pady=(0, 20))
        details_container, _ = self._build_details_with_photo(self.details_frame, user_data, is_match_tab=False)
        self._fill_detail_sections(details_container, user_data)

    def _fill_detail_sections(self, details_container, user_data):
        """Fill personal, fingerprint, service, and location sections into details_container."""
        personal_frame = ttk.LabelFrame(details_container, text="Personal Information", padding=10)
        personal_frame.pack(fill='x', pady=(0, 10))
        registration_id = resolve_registration_id(user_data)
        self._add_detail_row(
            personal_frame,
            "Registration ID:",
            registration_id if registration_id is not None else 'N/A',
        )
        self._add_detail_row(personal_frame, "Full Name:", user_data.get('full_name', 'N/A'))
        self._add_detail_row(personal_frame, "Passport Number:", user_data.get('passport_number', 'N/A'))
        self._add_detail_row(personal_frame, "Phone:", user_data.get('phone', 'N/A'))
        self._add_detail_row(personal_frame, "Father's Name:", user_data.get('father_name', 'N/A'))
        self._add_detail_row(personal_frame, "Birth Date:", self._format_date(user_data.get('birth_date')))
        self._add_detail_row(personal_frame, "Gender:", user_data.get('gender', 'N/A'))
        self._add_detail_row(personal_frame, "Nationality:", user_data.get('nationality', 'N/A'))
        self._add_detail_row(personal_frame, "Profession:", user_data.get('profession', 'N/A'))
        self._add_detail_row(personal_frame, "Religion:", user_data.get('religion', 'N/A'))
        self._add_detail_row(personal_frame, "Address:", user_data.get('address', 'N/A'))
        fingerprint_info = user_data.get('fingerprint', {})
        fp_status_frame = ttk.LabelFrame(details_container, text="Fingerprint Status", padding=10)
        fp_status_frame.pack(fill='x', pady=(0, 10))
        is_registered = fingerprint_info.get('registered', False)
        has_template = fingerprint_info.get('has_template', False)
        status_text = "✅ Registered" if is_registered else "❌ Not Registered"
        template_text = "✅ Template Available" if has_template else "❌ No Template"
        self._add_detail_row(fp_status_frame, "Registration Status:", status_text)
        self._add_detail_row(fp_status_frame, "Template Status:", template_text)
        service_frame = ttk.LabelFrame(details_container, text="Service Information", padding=10)
        service_frame.pack(fill='x', pady=(0, 10))
        self._add_detail_row(service_frame, "Amount:", f"৳{user_data.get('amount', 0)}")
        self._add_detail_row(service_frame, "Delivery Date:", self._format_date(user_data.get('delivery_date')))
        if user_data.get('branch') or user_data.get('country'):
            location_frame = ttk.LabelFrame(details_container, text="Location Information", padding=10)
            location_frame.pack(fill='x', pady=(0, 10))
            if user_data.get('branch'):
                branch = user_data['branch']
                self._add_detail_row(location_frame, "Branch Name:", branch.get('name', 'N/A'))
                self._add_detail_row(location_frame, "Branch Address:", branch.get('address', 'N/A'))
            if user_data.get('country'):
                country = user_data['country']
                self._add_detail_row(location_frame, "Country:", country.get('name', 'N/A'))
        
    def _add_detail_row(self, parent, label, value):
        """Add a detail row with label and value"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill='x', pady=2)
        
        label_widget = ttk.Label(row_frame, text=label, style='Heading.TLabel', width=20, anchor='w')
        label_widget.pack(side='left')
        
        value_widget = ttk.Label(row_frame, text=str(value) if value else 'N/A', style='Info.TLabel', anchor='w')
        value_widget.pack(side='left', fill='x', expand=True)
        
    def _format_date(self, date_str):
        """Format date string for display"""
        if not date_str:
            return 'N/A'
        try:
            # Parse the date and format it nicely
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date_obj.strftime('%B %d, %Y')
        except:
            return date_str

    def _find_photo_in_dict(self, obj, depth=0, max_depth=4):
        """Recursively find first non-empty string value for photo-like keys in dict/lists."""
        if depth > max_depth or obj is None:
            return None
        photo_keys = (
            'photo', 'image', 'image_url', 'avatar', 'photo_url', 'user_photo',
            'patient_photo', 'photo_path', 'profile_photo', 'passport_photo',
            'applicant_photo', 'picture', 'photo_path_url'
        )
        if isinstance(obj, dict):
            for key in photo_keys:
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            for v in obj.values():
                found = self._find_photo_in_dict(v, depth + 1, max_depth)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._find_photo_in_dict(item, depth + 1, max_depth)
                if found:
                    return found
        return None

    def _get_finger_image_source(self, user_data):
        """Get finger_image base64 string from API response."""
        if not isinstance(user_data, dict):
            return None
        for source in (user_data, user_data.get('fingerprint') or {}):
            raw = source.get('finger_image')
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        return None

    def _get_photo_source_and_emoji(self, user_data):
        """Get photo URL or base64 string from API response, and emoji. Returns (source_string or None, emoji)."""
        gender = (user_data.get('gender') or '').lower()
        emoji = '👩' if gender == 'female' else '👨'
        # Prefer top-level "photo" key (API returns photo URL here, e.g. with passport_number, full_name)
        photo_source = None
        if isinstance(user_data, dict):
            raw = user_data.get('photo')
            if isinstance(raw, str) and raw.strip():
                photo_source = raw.strip()
        if not photo_source:
            photo_source = self._find_photo_in_dict(user_data)
        if not photo_source:
            return None, emoji
        # Resolve relative paths (e.g. /storage/photos/patient_xxx.jpeg)
        if isinstance(photo_source, str) and photo_source.startswith('/') and not photo_source.startswith('//'):
            base = normalize_server_url(self.settings.get('server_url'))
            photo_source = base + photo_source
        return photo_source, emoji

    def _fetch_image_bytes(self, photo_source):
        """Fetch image bytes from URL or decode base64. Returns bytes or None. Runs in thread."""
        try:
            if isinstance(photo_source, str) and photo_source.startswith(('http://', 'https://')):
                headers = {'User-Agent': 'RTMS-Biometric-App/1.0'}
                r = requests.get(photo_source, timeout=20, headers=headers, verify=True)
                r.raise_for_status()
                return r.content
            elif isinstance(photo_source, str):
                return base64.b64decode(photo_source)
        except requests.exceptions.SSLError:
            try:
                r = requests.get(photo_source, timeout=20, headers={'User-Agent': 'RTMS-Biometric-App/1.0'}, verify=False)
                r.raise_for_status()
                return r.content
            except Exception:
                return None
        except Exception as e:
            log_error(f"Photo load failed: {e}")
            return None
        return None

    def _apply_photo_to_frame(self, photo_inner, image_bytes, emoji, is_match_tab):
        """Create PhotoImage from bytes and show in photo_inner (main thread). Keep ref on self."""
        try:
            if not photo_inner.winfo_exists():
                return
        except tk.TclError:
            return
        for w in photo_inner.winfo_children():
            w.destroy()
        ref_attr = '_match_photo_ref' if is_match_tab else '_register_photo_ref'
        setattr(self, ref_attr, [None])
        if image_bytes and HAS_PIL:
            try:
                img = Image.open(io.BytesIO(image_bytes))
                img = img.convert('RGB')
                img.thumbnail((280, 360), Image.Resampling.LANCZOS)
                photo_image = ImageTk.PhotoImage(img)
                getattr(self, ref_attr)[0] = photo_image
                lbl = ttk.Label(photo_inner, image=photo_image)
                lbl.pack(expand=True)
                return
            except Exception as e:
                log_error(f"Photo decode failed: {e}")
        lbl = tk.Label(photo_inner, text=emoji, font=('Segoe UI Emoji', 120), bg='#f8f9fa', fg='#495057')
        lbl.pack(expand=True, padx=20, pady=20)

    def _apply_finger_image_to_frame(self, finger_inner, image_bytes, is_match_tab):
        """Show fingerprint image or a cross when unavailable."""
        try:
            if not finger_inner.winfo_exists():
                return
        except tk.TclError:
            return
        for w in finger_inner.winfo_children():
            w.destroy()
        ref_attr = '_match_finger_ref' if is_match_tab else '_register_finger_ref'
        setattr(self, ref_attr, [None])
        display_bytes = decode_finger_image_bytes(image_bytes) if image_bytes else None
        if display_bytes and HAS_PIL:
            try:
                img = Image.open(io.BytesIO(display_bytes))
                img = img.convert('RGB')
                img.thumbnail((300, 400), Image.Resampling.LANCZOS)
                finger_image = ImageTk.PhotoImage(img)
                getattr(self, ref_attr)[0] = finger_image
                lbl = ttk.Label(finger_inner, image=finger_image)
                lbl.pack(expand=True)
                return
            except Exception as e:
                log_error(f"Finger image decode failed: {e}")
        lbl = tk.Label(finger_inner, text="✕", font=('Arial', 72), bg='#f8f9fa', fg='#dc3545')
        lbl.pack(expand=True, padx=20, pady=20)

    def _build_scrollable_details_panel(self, left_panel):
        """Left column scrollable area for user detail sections."""
        scroll_frame = ttk.Frame(left_panel)
        scroll_frame.pack(fill='y', expand=False)
        canvas = tk.Canvas(scroll_frame, height=420, bg='#f8f9fa')
        scrollbar = ttk.Scrollbar(scroll_frame, orient='vertical', command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        scrollbar.pack(side='left', fill='y')
        canvas.pack(side='left', fill='y', expand=False)
        return scrollable_frame

    def _build_details_with_photo(self, parent_frame, user_data, is_match_tab=False):
        """
        Build two-column layout: left = scrollable details, right = photo or emoji.
        Photo is loaded in a background thread so the UI stays responsive; ref is kept on self.
        """
        content = ttk.Frame(parent_frame)
        content.pack(fill='both', expand=True, padx=5, pady=5)
        left_panel = ttk.Frame(content)
        left_panel.pack(side='left', fill='y', expand=False)
        right_panel = ttk.Frame(content)
        right_panel.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=10)
        images_row = ttk.Frame(right_panel)
        images_row.pack(fill='both', expand=True)
        photo_frame = ttk.LabelFrame(images_row, text="Photo", padding=8)
        photo_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        photo_inner = ttk.Frame(photo_frame)
        photo_inner.pack(fill='both', expand=True)
        finger_frame = ttk.LabelFrame(images_row, text="Fingerprint", padding=8)
        finger_frame.pack(side='left', fill='both', expand=True)
        finger_inner = ttk.Frame(finger_frame)
        finger_inner.pack(fill='both', expand=True)
        gender = (user_data.get('gender') or '').lower()
        emoji = '👩' if gender == 'female' else '👨'
        loading_lbl = tk.Label(photo_inner, text="Loading…\n" + emoji, font=('Arial', 14), bg='#f8f9fa', fg='#495057')
        loading_lbl.pack(expand=True, padx=20, pady=20)
        finger_loading_lbl = tk.Label(finger_inner, text="Loading…", font=('Arial', 14), bg='#f8f9fa', fg='#495057')
        finger_loading_lbl.pack(expand=True, padx=20, pady=20)
        scrollable_frame = self._build_scrollable_details_panel(left_panel)
        photo_source, emoji = self._get_photo_source_and_emoji(user_data)
        if not photo_source or not HAS_PIL:
            loading_lbl.config(text=emoji, font=('Segoe UI Emoji', 120))
        else:
            def load_photo():
                data = self._fetch_image_bytes(photo_source)
                self.root.after(0, self._apply_photo_to_frame, photo_inner, data, emoji, is_match_tab)
            threading.Thread(target=load_photo, daemon=True).start()
        finger_source = self._get_finger_image_source(user_data)
        if finger_source and HAS_PIL:
            def load_finger():
                data = self._fetch_image_bytes(finger_source)
                self.root.after(0, self._apply_finger_image_to_frame, finger_inner, data, is_match_tab)
            threading.Thread(target=load_finger, daemon=True).start()
        else:
            finger_loading_lbl.destroy()
            self._apply_finger_image_to_frame(finger_inner, None, is_match_tab)
        return scrollable_frame, None

    def register_fingerprint(self):
        """Register fingerprint for the current user"""
        if not self.current_user_data:
            messagebox.showerror("Error", "No user data available")
            return
        
        # Check if user already has fingerprint registered
        fingerprint_info = self.current_user_data.get('fingerprint', {})
        is_registered = fingerprint_info.get('registered', False)
        
        if is_registered:
            # Ask for confirmation to re-register
            result = messagebox.askyesno(
                "Fingerprint Already Registered", 
                "This user already has a fingerprint registered. Do you want to re-register it?\n\n"
                "This will replace the existing fingerprint data."
            )
            if not result:
                return
            
        self._registration_is_update = bool(is_registered)
        self.registration_cancelled = False
        self.register_fp_btn.configure(state='disabled')
        self.cancel_register_btn.pack(side='left')
        status_text = "Re-registering fingerprint..." if is_registered else "Registering fingerprint..."
        self.register_status_label.configure(text=f"{status_text} Please follow scanner instructions.",
                                           style='Info.TLabel')
        log_info(f"Register tab: fingerprint registration started for {self.current_user_data.get('passport_number')}")
        thread = threading.Thread(target=self._register_fingerprint_thread)
        thread.daemon = True
        thread.start()

    def _cancel_registration(self):
        """Terminate the registration process so OS releases device handles; no invalid handle on retry."""
        self.registration_cancelled = True
        self.register_status_label.configure(text="Cancelling...", style='Info.TLabel')
        if getattr(self, '_registration_process', None) is not None:
            try:
                self._registration_process.terminate()
                self._registration_process.join(timeout=2.0)
                if self._registration_process.is_alive():
                    self._registration_process.kill()
            except Exception:
                pass
            self._registration_process = None
        self.root.after(0, self._finish_registration_cancelled)

    def _finish_registration_cancelled(self):
        """Called after cancel to reset UI (from main or polling thread)."""
        self.cancel_register_btn.pack_forget()
        self.register_fp_btn.configure(state='normal')
        self.register_status_label.configure(text="Registration cancelled.", style='Info.TLabel')
        messagebox.showinfo("Cancelled", "Fingerprint registration was cancelled.")

    def _register_fingerprint_thread(self):
        """Run registration in a separate process so killing it releases all device handles."""
        self._registration_process = None
        try:
            progress_queue = multiprocessing.Queue()
            result_queue = multiprocessing.Queue()
            p = multiprocessing.Process(target=_registration_worker_process, args=(progress_queue, result_queue))
            self._registration_process = p
            p.start()
            result_received = None
            while True:
                if self.registration_cancelled:
                    break
                try:
                    msg = progress_queue.get(timeout=0.3)
                    self.root.after(0, self._update_registration_status, msg)
                except multiprocessing.queues.Empty:
                    pass
                try:
                    result_received = result_queue.get_nowait()
                    break
                except multiprocessing.queues.Empty:
                    pass
                if not p.is_alive():
                    if result_received is None:
                        result_received = ('error', 'Process ended unexpectedly (cancelled or crashed).')
                    break
                time.sleep(0.05)
            if self._registration_process is not None:
                try:
                    p.join(timeout=1.0)
                except Exception:
                    pass
                self._registration_process = None
            if result_received is None:
                if self.registration_cancelled:
                    pass  # _finish_registration_cancelled already called from _cancel_registration
                else:
                    self.root.after(0, self._fingerprint_registration_error, "Registration process ended unexpectedly.")
                return
            status, value = result_received
            if status == 'error':
                self.root.after(0, self._fingerprint_registration_error, value)
                return
            if isinstance(value, tuple):
                template_b64, finger_image_b64 = value
            else:
                template_b64, finger_image_b64 = value, None
            self.root.after(0, self._update_registration_status, "📡 Sending fingerprint data to server...")
            passport_number = self.current_user_data.get('passport_number')
            api_data = {"passport_number": passport_number, "template": template_b64}
            if finger_image_b64:
                api_data["finger_image"] = finger_image_b64
            response = requests.post(
                self.fingerprint_api_url,
                json=api_data,
                headers=api_request_headers(self.auth_token),
                timeout=10
            )
            log_info(f"Register API response: {response.status_code} {response.text[:500]}")
            if response.status_code in [200, 201]:
                try:
                    result = response.json()
                    if result.get('success', False):
                        self.root.after(0, self._fingerprint_registration_success, finger_image_b64)
                    else:
                        self.root.after(0, self._fingerprint_registration_error, result.get('message', 'API registration failed'))
                except json.JSONDecodeError:
                    self.root.after(0, self._fingerprint_registration_error, "Invalid JSON response from API")
            else:
                self.root.after(0, self._fingerprint_registration_error, f"API Error: {response.status_code} - {response.text}")
        except Exception as e:
            log_exception("Register tab: registration thread failed", e)
            self.root.after(0, self._fingerprint_registration_error, str(e))
        finally:
            self._registration_process = None
    
    def _update_registration_status(self, message):
        """Update registration status in GUI"""
        self.register_status_label.configure(text=message, style='Info.TLabel')
            
    def _fingerprint_registration_success(self, finger_image_b64=None):
        """Handle successful fingerprint registration"""
        action = "update" if self._registration_is_update else "add"
        log_info("Register tab: fingerprint registered successfully")
        if finger_image_b64 and self.current_user_data:
            fingerprint_info = self.current_user_data.setdefault('fingerprint', {})
            fingerprint_info['finger_image'] = finger_image_b64
            fingerprint_info['registered'] = True
            self._display_user_details(self.current_user_data)
        self.cancel_register_btn.pack_forget()
        self.register_status_label.configure(text="Fingerprint registered successfully!", style='Success.TLabel')
        self.register_fp_btn.configure(state='normal')
        self._record_history(
            action,
            "success",
            message=(
                "Fingerprint updated successfully"
                if action == "update"
                else "Fingerprint registered successfully"
            ),
            subject=self.current_user_data,
        )
        messagebox.showinfo("Success", "Fingerprint has been registered successfully!")

    def _fingerprint_registration_error(self, error_message):
        """Handle fingerprint registration error"""
        action = "update" if self._registration_is_update else "add"
        log_error(f"Register tab: {error_message}")
        self.cancel_register_btn.pack_forget()
        self.register_status_label.configure(text=f"Registration failed: {error_message}", style='Error.TLabel')
        self.register_fp_btn.configure(state='normal')
        self._record_history(
            action,
            "failed",
            message=error_message,
            subject=self.current_user_data,
        )
        messagebox.showerror("Error", f"Fingerprint registration failed: {error_message}")
        
    def _on_auto_print_toggled(self):
        """Persist Auto Print checkbox across sessions."""
        if not self.can_print_barcode or self.auto_print_var is None:
            return
        self.settings["auto_print_barcode"] = bool(self.auto_print_var.get())
        if self.save_settings_to_file(self.settings):
            log_info(f"Auto Print preference saved: {self.settings['auto_print_barcode']}")
        else:
            log_error("Failed to save Auto Print preference")

    def _set_print_status(self, status_label, message, style="Info.TLabel"):
        if status_label is not None:
            try:
                status_label.configure(text=message, style=style)
            except Exception:
                pass

    def _print_barcode_for_user(self, user_data, *, auto=False, status_label=None):
        """Print Code128 of the patient's printable serial (non-blocking)."""
        if not self.can_print_barcode:
            return
        serial = resolve_registration_id(user_data)
        if not serial:
            msg = "No printable serial (registration_id / daily_serial_no) available."
            log_error(f"Barcode print: {msg}")
            self._set_print_status(status_label, f"❌ {msg}", "Error.TLabel")
            if not auto:
                messagebox.showerror("Print Barcode", msg)
            return

        if auto and serial == self._last_auto_printed_serial:
            log_info(f"Auto Print skipped (already printed for {serial})")
            return

        self._set_print_status(
            status_label,
            f"Printing barcode ({serial})...",
            "Info.TLabel",
        )
        log_info(f"Barcode print {'(auto)' if auto else '(manual)'}: {serial}")

        def on_done(ok, status, detail):
            def apply():
                if ok:
                    if auto:
                        self._last_auto_printed_serial = serial
                    style = "Success.TLabel"
                    prefix = "✅"
                    if status == "opened":
                        prefix = "ℹ️"
                    self._set_print_status(status_label, f"{prefix} {detail}", style)
                    log_info(f"Barcode print result: {detail}")
                else:
                    self._set_print_status(status_label, f"❌ {detail}", "Error.TLabel")
                    log_error(f"Barcode print failed: {detail}")
                    if not auto:
                        messagebox.showerror("Print Barcode", detail)

            self.root.after(0, apply)

        print_barcode_async(serial, prefer_silent=True, on_done=on_done)

    def _maybe_auto_print(self, user_data, status_label=None):
        """Auto-print after match/selection when Auto Print is enabled."""
        if not self.can_print_barcode or self.auto_print_var is None:
            return
        if not self.auto_print_var.get():
            return
        if not user_data:
            return
        self._print_barcode_for_user(user_data, auto=True, status_label=status_label)

    def _print_match_barcode(self):
        """Manual Print Barcode on Match tab."""
        if not self.current_match_user_data:
            messagebox.showerror("Print Barcode", "Please search for a patient first.")
            return
        self._print_barcode_for_user(
            self.current_match_user_data,
            auto=False,
            status_label=self.match_result_label,
        )

    def _print_auto_search_barcode(self):
        """Manual Print Barcode on Auto Search tab."""
        if not self.current_auto_search_user_data:
            messagebox.showerror("Print Barcode", "Please identify a patient first.")
            return
        self._print_barcode_for_user(
            self.current_auto_search_user_data,
            auto=False,
            status_label=self.auto_search_status_label,
        )

    def match_fingerprint(self):
        """Match fingerprint with stored template"""
        if not self.current_match_user_data:
            messagebox.showerror("Error", "Please search for a passport first")
            return
            
        self.match_cancelled = False
        self.match_btn.configure(state='disabled')
        self.cancel_match_btn.pack(side='left')
        self.match_result_label.configure(text="Matching fingerprint... Please place finger on scanner.", 
                                        style='Info.TLabel')
        
        log_info(f"Match tab: fingerprint match started for {self.current_match_user_data.get('passport_number')}")
        # Run matching in separate thread
        thread = threading.Thread(target=self._match_fingerprint_thread)
        thread.daemon = True
        thread.start()
        
    def _match_fingerprint_thread(self):
        """Match fingerprint in separate thread"""
        try:
            if not self.current_match_user_data:
                self.root.after(0, self._handle_match_error, "No user data available")
                return
            
            # Get stored template from API
            passport_number = self.current_match_user_data.get('passport_number')
            if not passport_number:
                self.root.after(0, self._handle_match_error, "No passport number available")
                return
            
            # Update GUI: Getting stored template
            self.root.after(0, self._update_match_status, "📡 Retrieving stored fingerprint template...")
            
            # Get stored template from fingerprint lookup API
            lookup_response = requests.get(
                f"{self.fingerprint_lookup_url}/{passport_number}",
                headers=api_request_headers(self.auth_token),
                timeout=10,
            )
            log_info(
                f"Match tab: template lookup {lookup_response.url} status={lookup_response.status_code}"
            )
            
            if lookup_response.status_code != 200:
                self.root.after(0, self._handle_match_error, f"Failed to retrieve stored template: {lookup_response.status_code}")
                return
            
            lookup_data = lookup_response.json()
            if not lookup_data.get('success'):
                self.root.after(0, self._handle_match_error, lookup_data.get('message', 'Failed to retrieve template'))
                return
            
            lookup_payload = lookup_data.get('data') or {}
            stored_template_b64 = lookup_payload.get('template')
            if not stored_template_b64:
                self.root.after(0, self._handle_match_error, "No template found in API response")
                return
            registration_id = (
                lookup_payload.get('registration_id')
                or lookup_payload.get('registration_number')
            )
            if registration_id is not None:
                self.root.after(0, self._apply_match_registration_id, registration_id)
            
            # Run device capture and match in a separate process so handle is released when done
            progress_queue = multiprocessing.Queue()
            result_queue = multiprocessing.Queue()
            p = multiprocessing.Process(target=_match_worker_process, args=(progress_queue, result_queue, stored_template_b64))
            self._match_process = p
            p.start()
            result_received = None
            while True:
                if self.match_cancelled:
                    break
                try:
                    msg = progress_queue.get(timeout=0.3)
                    self.root.after(0, self._update_match_status, msg)
                except multiprocessing.queues.Empty:
                    pass
                try:
                    result_received = result_queue.get_nowait()
                    break
                except multiprocessing.queues.Empty:
                    pass
                if not p.is_alive():
                    if result_received is None:
                        result_received = ('error', 'Match process ended unexpectedly.')
                    break
                time.sleep(0.05)
            if self._match_process is not None:
                try:
                    p.join(timeout=1.0)
                except Exception:
                    pass
                self._match_process = None
            if result_received is None:
                if self.match_cancelled:
                    pass  # _finish_match_cancelled already called from _cancel_match
                else:
                    self.root.after(0, self._handle_match_error, "Match process ended without result.")
                return
            status, value = result_received
            if status == 'error':
                self.root.after(0, self._handle_match_error, value)
                return
            self.root.after(0, self._handle_match_result, value)
            
        except Exception as e:
            log_exception("Match tab: match thread failed", e)
            self.root.after(0, self._handle_match_error, str(e))

    def _cancel_match(self):
        """Terminate the match process and reset UI."""
        self.match_cancelled = True
        self.match_result_label.configure(text="Cancelling...", style='Info.TLabel')
        if getattr(self, '_match_process', None) is not None:
            try:
                self._match_process.terminate()
                self._match_process.join(timeout=2.0)
                if self._match_process.is_alive():
                    self._match_process.kill()
            except Exception:
                pass
            self._match_process = None
        self.root.after(0, self._finish_match_cancelled)

    def _finish_match_cancelled(self):
        """Reset Match tab UI after cancel."""
        self.cancel_match_btn.pack_forget()
        self.match_btn.configure(state='normal')
        self.match_result_label.configure(text="Match cancelled.", style='Info.TLabel')
        messagebox.showinfo("Cancelled", "Fingerprint match was cancelled.")

    def _update_match_status(self, message):
        """Update match status in GUI"""
        self.match_result_label.configure(text=message, style='Info.TLabel')

    def _apply_match_registration_id(self, registration_id):
        """Merge registration_id from match API into displayed user details."""
        if not self.current_match_user_data:
            return
        updated = dict(self.current_match_user_data)
        updated["registration_id"] = registration_id
        self.current_match_user_data = updated
        self._display_match_user_details(updated)
            
    def _handle_match_result(self, result):
        """Handle fingerprint match result"""
        log_info(f"Match tab: result={'match' if result else 'no match'}")
        self.cancel_match_btn.pack_forget()
        self.match_btn.configure(state='normal')
        subject = self.current_match_user_data
        matched_fields = subject_fields_from_user_data(subject) if subject else {}
        if result:
            self.match_result_label.configure(text="✅ Match successful", 
                                            style='MatchSuccess.TLabel')
            self._record_history(
                "match",
                "success",
                message="Fingerprint matched",
                subject=subject,
                matched_passport_number=matched_fields.get("passport_number"),
                matched_fingerprint_id=matched_fields.get("fingerprint_id"),
            )
            messagebox.showinfo("Match Success", "Fingerprint matched successfully")
            self._maybe_auto_print(
                self.current_match_user_data,
                status_label=self.match_result_label,
            )
        else:
            self.match_result_label.configure(text="❌ Does not match", 
                                            style='MatchNoMatch.TLabel')
            self._record_history(
                "match",
                "failed",
                message="Fingerprint does not match",
                subject=subject,
                passport_number=matched_fields.get("passport_number"),
            )
            messagebox.showwarning("No Match", "Fingerprint does not match")
            
    def _handle_match_error(self, error_message):
        """Handle fingerprint match error"""
        log_error(f"Match tab: {error_message}")
        self.cancel_match_btn.pack_forget()
        self.match_btn.configure(state='normal')
        self.match_result_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        self._record_history(
            "match",
            "failed",
            message=error_message,
            subject=self.current_match_user_data,
        )
        messagebox.showerror("Error", f"Matching failed: {error_message}")
    
    def load_settings(self):
        """Load settings from JSON file"""
        settings_file = settings_path()
        default_settings = {
            "server_url": "https://rtmsbd.com",
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    return settings
            else:
                # Create default settings file
                with open(settings_file, 'w') as f:
                    json.dump(default_settings, f, indent=2)
                return default_settings
        except Exception as e:
            log_exception("Error loading settings", e)
            return default_settings
    
    def save_settings_to_file(self, settings):
        """Save settings to JSON file"""
        settings_file = settings_path()
        try:
            settings["last_updated"] = datetime.now().isoformat()
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            return True
        except Exception as e:
            log_exception("Error saving settings", e)
            return False
    
    def save_settings_ui(self):
        """Save settings from UI"""
        new_url = self.server_url_entry.get().strip()
        
        # Validate URL
        if not new_url:
            messagebox.showerror("Error", "Server URL cannot be empty")
            return
        
        if not (new_url.startswith('http://') or new_url.startswith('https://')):
            messagebox.showerror("Error", "Server URL must start with http:// or https://")
            return
        
        # Update settings
        self.settings["server_url"] = new_url
        
        # Save to file
        if self.save_settings_to_file(self.settings):
            # Update API URLs
            base = new_url.rstrip('/')
            self.api_base_url = base + "/api/v1/service-request/passport/"
            self.fingerprint_api_url = base + "/api/v1/fingerprint/register"
            self.fingerprint_lookup_url = base + "/api/v1/finger/passport"
            self.fingerprint_identify_url = base + "/api/v1/finger/identify"
            self.finger_scan_history_url = base + "/api/v1/finger-scan/history"
            self.login_url_base = base
            
            log_info(f"Settings saved: server_url={base}")
            self.settings_status_label.configure(text="✅ Settings saved successfully!", style='Success.TLabel')
            messagebox.showinfo("Success", "Settings have been saved successfully!")
        else:
            log_error("Failed to save settings to file")
            self.settings_status_label.configure(text="❌ Failed to save settings", style='Error.TLabel')
            messagebox.showerror("Error", "Failed to save settings to file")
    
    def test_connection(self):
        """Test connection to the server"""
        test_url = self.server_url_entry.get().strip()
        
        if not test_url:
            messagebox.showerror("Error", "Please enter a server URL")
            return
        
        self.test_btn.configure(state='disabled')
        self.settings_status_label.configure(text="Testing connection...", style='Info.TLabel')
        
        # Run test in separate thread
        thread = threading.Thread(target=self._test_connection_thread, args=(test_url,))
        thread.daemon = True
        thread.start()
    
    def _test_connection_thread(self, test_url):
        """Test connection in separate thread"""
        try:
            # Test with a simple GET request to the base URL
            response = requests.get(test_url, timeout=5)
            self.root.after(0, self._handle_test_result, True, f"Connection successful! Status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.root.after(0, self._handle_test_result, False, str(e))
    
    def _handle_test_result(self, success, message):
        """Handle test connection result"""
        self.test_btn.configure(state='normal')
        if success:
            log_info(f"Connection test: {message}")
        else:
            log_error(f"Connection test failed: {message}")
        if success:
            self.settings_status_label.configure(text=f"✅ {message}", style='Success.TLabel')
        else:
            self.settings_status_label.configure(text=f"❌ Connection failed: {message}", style='Error.TLabel')
    
    def reset_to_default(self):
        """Reset server URL to default"""
        default_url = "https://rtmsbd.com"
        self.server_url_entry.delete(0, tk.END)
        self.server_url_entry.insert(0, default_url)
        self.settings_status_label.configure(text="Reset to default URL", style='Info.TLabel')
    
    def refresh_db_info(self):
        """Refresh database information"""
        try:
            fingerprints = list_fingers()
            count = len(fingerprints) if fingerprints else 0
            
            db_info = f"Total fingerprints stored: {count}\n"
            if count > 0:
                db_info += f"Fingerprint IDs: {', '.join([str(fp[0]) for fp in fingerprints[:5]])}"
                if count > 5:
                    db_info += f" and {count - 5} more..."
            
            self.db_info_label.configure(text=db_info)
        except Exception as e:
            log_exception("Error reading local database info", e)
            self.db_info_label.configure(text=f"Error reading database: {e}")
            
    def match_search_passport(self):
        """Search for passport information via API"""
        passport_number = self.match_passport_entry.get().strip()
        if not passport_number:
            messagebox.showerror("Error", "Please enter a passport number")
            return
            
        # Disable search button and show loading
        self.match_search_btn.configure(state='disabled')
        self.match_loading_label.configure(text="Searching...", style='Info.TLabel')
        log_info(f"Match tab: passport search {passport_number}")
        
        # Run API call in separate thread to prevent UI freezing
        thread = threading.Thread(target=self._match_api_search_thread, args=(passport_number,))
        thread.daemon = True
        thread.start()
        
    def _match_api_search_thread(self, passport_number):
        """API search in separate thread"""
        try:
            url = f"{self.api_base_url}{passport_number}"
            response = requests.get(url, headers=api_request_headers(self.auth_token), timeout=10)
            log_info(f"Match tab: passport API {url} status={response.status_code}")
            user_data = None
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('success') and isinstance(data.get('data'), dict):
                        user_data = enrich_user_data_with_registration_id(
                            data['data'], self.fingerprint_lookup_url, self.auth_token
                        )
                except json.JSONDecodeError:
                    pass
            
            # Schedule UI update in main thread
            self.root.after(0, self._handle_match_api_response, response, passport_number, user_data)
            
        except requests.exceptions.RequestException as e:
            log_exception(f"Match tab: passport search failed ({passport_number})", e)
            self.root.after(0, self._handle_match_api_error, str(e), passport_number)
            
    def _handle_match_api_response(self, response, passport_number, enriched_user_data=None):
        """Handle API response in main thread"""
        try:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.current_match_user_data = enriched_user_data if enriched_user_data is not None else data.get('data')
                    self._last_auto_printed_serial = None  # new patient selection
                    self._display_match_user_details(self.current_match_user_data)
                    self.match_loading_label.configure(text="User found successfully!", style='Success.TLabel')
                    log_info(f"Match tab: user found {passport_number}")
                    self._record_history(
                        "search",
                        "success",
                        message="Record found",
                        subject=self.current_match_user_data,
                        passport_number=passport_number,
                    )
                    self._maybe_auto_print(
                        self.current_match_user_data,
                        status_label=self.match_result_label,
                    )
                else:
                    self._handle_match_api_error(data.get('message', 'Unknown error'), passport_number)
            else:
                self._handle_match_api_error(f"HTTP {response.status_code}: {response.text}", passport_number)
                
        except json.JSONDecodeError:
            self._handle_match_api_error("Invalid response format", passport_number)
        except Exception as e:
            self._handle_match_api_error(str(e), passport_number)
        finally:
            self.match_search_btn.configure(state='normal')
            
    def _handle_match_api_error(self, error_message, passport_number=None):
        """Handle API errors"""
        log_error(f"Match tab: {error_message}")
        self.match_loading_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        self.match_search_btn.configure(state='normal')
        self.match_details_frame.pack_forget()
        self.current_match_user_data = None
        self._last_auto_printed_serial = None
        self._record_history(
            "search",
            "failed",
            message=error_message,
            passport_number=passport_number,
        )
        
    def _display_match_user_details(self, user_data):
        """Display user details with left (details) and right (photo/emoji) layout"""
        user_data = self._ensure_registration_id(user_data)
        self.current_match_user_data = user_data
        for widget in self.match_details_frame.winfo_children():
            widget.destroy()
        self.match_details_frame.pack(fill='x', pady=(0, 20))
        details_container, _ = self._build_details_with_photo(self.match_details_frame, user_data, is_match_tab=True)
        self._fill_detail_sections(details_container, user_data)

    def auto_search(self):
        """Capture fingerprint and identify user via API (no passport number required)."""
        self.auto_search_cancelled = False
        self.auto_search_btn.configure(state='disabled')
        self.cancel_auto_search_btn.pack(side='left')
        self.auto_search_status_label.configure(
            text="Scanning fingerprint... Please place finger on scanner.",
            style='Info.TLabel',
        )
        self.auto_search_details_frame.pack_forget()
        self.current_auto_search_user_data = None
        self._last_auto_printed_serial = None
        log_info("Auto Search: started")
        thread = threading.Thread(target=self._auto_search_thread)
        thread.daemon = True
        thread.start()

    def _cancel_auto_search(self):
        """Terminate auto search capture process and reset UI."""
        self.auto_search_cancelled = True
        self.auto_search_status_label.configure(text="Cancelling...", style='Info.TLabel')
        if getattr(self, '_auto_search_process', None) is not None:
            try:
                self._auto_search_process.terminate()
                self._auto_search_process.join(timeout=2.0)
                if self._auto_search_process.is_alive():
                    self._auto_search_process.kill()
            except Exception:
                pass
            self._auto_search_process = None
        self.root.after(0, self._finish_auto_search_cancelled)

    def _finish_auto_search_cancelled(self):
        log_info("Auto Search: cancelled")
        self.cancel_auto_search_btn.pack_forget()
        self.auto_search_btn.configure(state='normal')
        self.auto_search_status_label.configure(text="Auto search cancelled.", style='Info.TLabel')

    def _update_auto_search_status(self, message):
        self.auto_search_status_label.configure(text=message, style='Info.TLabel')

    def _api_auth_headers(self):
        return api_request_headers(self.auth_token)

    def _run_sequential_match(self, live_template_b64, records):
        """Run DBMatch against records in a subprocess; return {record, score} for page best."""
        if not records:
            return None
        progress_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        p = multiprocessing.Process(
            target=_sequential_match_worker_process,
            args=(progress_queue, result_queue, live_template_b64, records),
        )
        self._auto_search_process = p
        p.start()
        result_received = None
        while True:
            if self.auto_search_cancelled:
                break
            try:
                msg = progress_queue.get(timeout=0.3)
                self.root.after(0, self._update_auto_search_status, f"Searching... {msg}")
            except multiprocessing.queues.Empty:
                pass
            try:
                result_received = result_queue.get_nowait()
                break
            except multiprocessing.queues.Empty:
                pass
            if not p.is_alive():
                if result_received is None:
                    result_received = ("error", "Match process ended unexpectedly.")
                break
            time.sleep(0.05)
        if self._auto_search_process is not None:
            try:
                p.join(timeout=1.0)
            except Exception:
                pass
            self._auto_search_process = None
        if self.auto_search_cancelled:
            return None
        if result_received is None:
            raise RuntimeError("Match process ended without result.")
        status, value = result_received
        if status == "error":
            raise RuntimeError(value)
        return value

    def _load_passport_user_data(self, passport_number):
        """Fetch full user payload for a passport number."""
        response = requests.get(
            f"{self.api_base_url}{passport_number}",
            headers=self._api_auth_headers(),
            timeout=15,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to load passport details: {response.status_code}")
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(payload.get("message", "Failed to load passport details"))
        user_data = payload.get("data")
        return enrich_user_data_with_registration_id(
            user_data, self.fingerprint_lookup_url, self.auth_token
        )

    def _auto_search_thread(self):
        """Capture fingerprint, list templates page-by-page, match sequentially until found."""
        self._auto_search_process = None
        try:
            progress_queue = multiprocessing.Queue()
            result_queue = multiprocessing.Queue()
            p = multiprocessing.Process(
                target=_capture_worker_process,
                args=(progress_queue, result_queue),
            )
            self._auto_search_process = p
            p.start()
            result_received = None
            while True:
                if self.auto_search_cancelled:
                    break
                try:
                    msg = progress_queue.get(timeout=0.3)
                    self.root.after(0, self._update_auto_search_status, msg)
                except multiprocessing.queues.Empty:
                    pass
                try:
                    result_received = result_queue.get_nowait()
                    break
                except multiprocessing.queues.Empty:
                    pass
                if not p.is_alive():
                    if result_received is None:
                        result_received = ('error', 'Capture process ended unexpectedly.')
                    break
                time.sleep(0.05)
            if self._auto_search_process is not None:
                try:
                    p.join(timeout=1.0)
                except Exception:
                    pass
                self._auto_search_process = None
            if self.auto_search_cancelled:
                return
            if result_received is None:
                self.root.after(0, self._handle_auto_search_error, "Capture process ended without result.", "scan")
                return
            status, value = result_received
            if status == 'error':
                self.root.after(0, self._handle_auto_search_error, value, "scan")
                return

            live_template_b64 = value
            self._record_history("scan", "success", message="Fingerprint captured")
            headers = self._api_auth_headers()
            page = 1
            last_page = None
            compared_total = 0
            best_score = 0
            best_record = None

            self.root.after(0, self._update_auto_search_status, "Searching...")
            branch_id = resolve_branch_id(self.user_info, self.settings)
            if branch_id is not None:
                log_info(f"Auto Search: fingerprint captured, searching branch_id={branch_id}")
            else:
                log_info("Auto Search: fingerprint captured, searching database (all branches)")

            while not self.auto_search_cancelled:
                page_label = f"page {page}" + (f"/{last_page}" if last_page else "")
                self.root.after(
                    0,
                    self._update_auto_search_status,
                    f"Searching... loading {page_label} ({compared_total} records checked)",
                )
                params = {"limit": IDENTIFY_PAGE_LIMIT, "page": page}
                if branch_id is not None:
                    params["branch_id"] = branch_id
                response = requests.get(
                    self.fingerprint_identify_url,
                    params=params,
                    headers=headers,
                    timeout=60,
                )
                if response.status_code != 200:
                    err = f"Fingerprint list API error: {response.status_code} - {response.text}"
                    log_error(f"Auto Search: {err}")
                    self.root.after(0, self._handle_auto_search_error, err)
                    return
                try:
                    payload = response.json()
                except json.JSONDecodeError:
                    self.root.after(0, self._handle_auto_search_error, "Invalid JSON from fingerprint list API")
                    return
                if not payload.get("success"):
                    self.root.after(
                        0,
                        self._handle_auto_search_error,
                        payload.get("message", "Failed to fetch fingerprint records"),
                    )
                    return

                pagination = payload.get("pagination") or {}
                last_page = pagination.get("last_page", page)
                records = payload.get("data") or []
                if not records:
                    break

                self.root.after(
                    0,
                    self._update_auto_search_status,
                    f"Searching... {page_label} — comparing {len(records)} templates",
                )
                page_result = self._run_sequential_match(live_template_b64, records)
                if self.auto_search_cancelled:
                    return
                if page_result:
                    page_score = page_result.get("score", 0)
                    page_record = page_result.get("record")
                    if page_score > best_score and page_record:
                        best_score = page_score
                        best_record = page_record
                        log_info(
                            f"Auto Search: new best score {best_score} "
                            f"passport={page_record.get('passport_number')}"
                        )
                    self.root.after(
                        0,
                        self._update_auto_search_status,
                        f"Searching... best score so far: {best_score} (need {MATCH_SCORE_THRESHOLD}+)",
                    )
                    if best_score >= MATCH_SCORE_EARLY_EXIT:
                        break

                compared_total += len(records)
                if page >= last_page:
                    break
                page += 1

            if self.auto_search_cancelled:
                return
            if best_record and best_score >= MATCH_SCORE_THRESHOLD:
                passport_number = best_record.get("passport_number")
                if not passport_number:
                    self.root.after(
                        0,
                        self._handle_auto_search_error,
                        "Match found but passport number missing in API record.",
                    )
                    return
                self.root.after(
                    0,
                    self._update_auto_search_status,
                    f"Searching... match found ({passport_number}, score {best_score}), loading details...",
                )
                user_data = self._load_passport_user_data(passport_number)
                registration_id = (
                    best_record.get("registration_id")
                    or best_record.get("registration_number")
                )
                if registration_id is not None and user_data is not None:
                    user_data = dict(user_data)
                    user_data["registration_id"] = registration_id
                self.root.after(0, self._handle_auto_search_success, user_data, best_score)
                return
            msg = (
                f"No matching fingerprint found ({compared_total} records checked, "
                f"best score {best_score})."
            )
            log_info(f"Auto Search: {msg}")
            self.root.after(0, self._handle_auto_search_error, msg)
        except Exception as e:
            log_exception("Auto Search: thread failed", e)
            self.root.after(0, self._handle_auto_search_error, str(e))
        finally:
            self._auto_search_process = None

    def _handle_auto_search_success(self, user_data, match_score=None):
        self.cancel_auto_search_btn.pack_forget()
        self.auto_search_btn.configure(state='normal')
        if not user_data:
            self._handle_auto_search_error("No user data returned")
            return
        self.current_auto_search_user_data = user_data
        self._display_auto_search_user_details(user_data)
        name = user_data.get('full_name') or user_data.get('passport_number') or 'User'
        score_text = f" (score {match_score})" if match_score is not None else ""
        log_info(f"Auto Search: match found {name}{score_text}")
        self.auto_search_status_label.configure(
            text=f"✅ Match found: {name}{score_text}",
            style='Success.TLabel',
        )
        matched_fields = subject_fields_from_user_data(user_data)
        self._record_history(
            "match",
            "success",
            message=f"Fingerprint matched{score_text}",
            subject=user_data,
            matched_passport_number=matched_fields.get("passport_number"),
            matched_fingerprint_id=matched_fields.get("fingerprint_id"),
            match_score=match_score,
        )
        messagebox.showinfo("Auto Search", f"User identified: {name}{score_text}")
        self._maybe_auto_print(
            self.current_auto_search_user_data,
            status_label=self.auto_search_status_label,
        )

    def _handle_auto_search_error(self, error_message, history_action="match"):
        if error_message and "No matching fingerprint" in str(error_message):
            log_info(f"Auto Search: {error_message}")
        else:
            log_error(f"Auto Search: {error_message}")
        self.cancel_auto_search_btn.pack_forget()
        self.auto_search_btn.configure(state='normal')
        self.auto_search_status_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        self.auto_search_details_frame.pack_forget()
        self.current_auto_search_user_data = None
        self._last_auto_printed_serial = None
        self._record_history(
            history_action,
            "failed",
            message=error_message,
        )
        if error_message and "No matching fingerprint" not in str(error_message):
            messagebox.showerror("Auto Search", str(error_message))
        else:
            messagebox.showwarning("Auto Search", str(error_message))

    def _display_auto_search_user_details(self, user_data):
        user_data = self._ensure_registration_id(user_data)
        self.current_auto_search_user_data = user_data
        for widget in self.auto_search_details_frame.winfo_children():
            widget.destroy()
        self.auto_search_details_frame.pack(fill='both', expand=True, pady=(0, 0))
        details_container, _ = self._build_details_with_photo(
            self.auto_search_details_frame, user_data, is_match_tab=True
        )
        self._fill_detail_sections(details_container, user_data)


def run_app():
    install_global_exception_logger()
    log_info(f"=== RTMS Biometric System started (log file: {logs_path()}) ===")
    root = tk.Tk()
    root.geometry("420x360")
    root.configure(bg="#f0f0f0")

    def show_login():
        for w in root.winfo_children():
            w.destroy()
        root.geometry("420x360")
        LoginScreen(root, on_success=on_login_success)

    def on_login_success(token, user_info):
        for w in root.winfo_children():
            w.destroy()
        root.geometry("1100x850")
        FingerprintApp(root, auth_token=token, user_info=user_info, on_logout=show_login)

    saved = load_saved_session()
    if saved:
        token, user_info = saved
        log_info(
            f"Restored Remember me session: {user_info.get('email')} "
            f"role={user_info.get('role')}"
        )
        on_login_success(token, user_info)
    else:
        show_login()
    root.mainloop()
