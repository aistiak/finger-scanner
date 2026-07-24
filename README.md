# RTMS Biometric App

Self-contained Windows desktop client for RTMS fingerprint registration, matching, and auto search.

## Layout

| File | Purpose |
|------|---------|
| `main.py` | Entry point — starts the GUI |
| `lib.py` | Application logic (login, tabs, API, local DB helpers) |
| `fingerprint_workers.py` | Scanner worker processes and finger-image encode/decode helpers |
| `requirements.txt` | Python dependencies |
| `app_settings.json` | Default server URL (created/updated at runtime next to the exe when built) |
| `build.bat` | One-click Windows build (venv + PyInstaller) |
| `fingerprint_app.spec` | PyInstaller configuration |

Runtime files (next to `main.py` when developing, or next to `FingerprintApp.exe` when deployed):

- `app_settings.json` — server URL
- `fingerprints-1.db` — local SQLite cache (settings tab info only; templates live on the API)
- `logs.txt` — application and error logs (`[INFO]` / `[ERROR]` with timestamps)

## Prerequisites

- Windows 10/11
- Python 3.10+ (64-bit recommended)
- ZKTeco / ZKFP2 fingerprint scanner drivers installed
- Network access to your RTMS Laravel API

## Run from source

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build Windows executable

```bat
build.bat
```

Output:

- `dist\FingerprintApp.exe`
- `dist\app_settings.json` (copied automatically after build)

Distribute **both** files in the same folder. On first run, settings and `fingerprints-1.db` are read/written beside the executable.

### Manual build

```bat
venv\Scripts\activate
pip install -r requirements.txt
pyinstaller --noconfirm fingerprint_app.spec
```

## Features (by role)

| Tab | Who sees it |
|-----|-------------|
| Register | `super_admin`, beman backdoor, `frontdesk` |
| Match | All roles except `frontdesk` |
| Auto Search | **All roles** |
| Settings | **All roles** |

**Auto Search** scans a fingerprint, then:

1. Fetches stored templates from `GET /api/v1/finger/identify?limit=50&page=N` (paginated list).
2. Compares your scan against each template on the client using the ZKTeco matcher (`DBMatch`), page by page, until a match is found.
3. Loads full passport details for the matched `passport_number`.

The UI shows **Searching...** with page and record progress while this runs. With ~7k enrolled prints, a worst-case search can take several minutes.

## API endpoints used

Base URL comes from **Settings** (`server_url`), e.g. `http://rtmsbd.com`:

| Method | Path |
|--------|------|
| POST | `/api/v1/login` |
| POST | `/api/v1/logout` |
| GET | `/api/v1/service-request/passport/{passport_number}` |
| POST | `/api/v1/fingerprint/register` |
| GET | `/api/v1/finger/passport/{passport_number}` |
| GET | `/api/v1/finger/identify?limit=&page=` (template list for auto search) |
| POST | `/api/v1/finger-scan/history` (action audit: login/logout/add/scan/match/search/update) |

## Troubleshooting

- **Device not found** — Install ZKFP2 drivers; close other apps using the scanner; run as administrator if needed.
- **Build: module not found** — Activate `venv` and run `pip install -r requirements.txt` before `build.bat`.
- **Build: Access denied** — Close `FingerprintApp.exe` if it is running, then rebuild.
- **Identify / auto search fails** — Ensure Laravel exposes `POST /api/v1/finger/identify` and returns `success` with `passport_number` or full user `data`.

## Development notes

All application code lives at the repo root (`main.py`, `lib.py`, `fingerprint_workers.py`).
