# Development

## Activate the virtual environment

From the project root (PowerShell or Command Prompt):

```bat
venv\Scripts\activate
```

You should see `(venv)` at the start of the prompt.

To deactivate later:

```bat
deactivate
```

## Run the app

With the venv activated:

```bat
python main.py
```

## First-time setup (if needed)

If `venv` is missing or dependencies are not installed:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build the Windows executable

From the project root (Command Prompt):

```bat
build.bat
```

This creates/activates `venv`, installs dependencies, and runs PyInstaller.

Output:

- `dist\FingerprintApp.exe`
- `dist\app_settings.json`

Close `FingerprintApp.exe` if it is already running before rebuilding.

### Manual build

With the venv activated:

```bat
pip install -r requirements.txt
pyinstaller --noconfirm fingerprint_app.spec
```
