@echo off
REM Use x64 Python venv (required for ZKFinger x64 SDK on Windows ARM)
cd /d "%~dp0"
if exist ".venv-x64\Scripts\python.exe" (
    ".venv-x64\Scripts\python.exe" main.py
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    echo No virtual environment found. Run: python -m venv .venv-x64
    exit /b 1
)
