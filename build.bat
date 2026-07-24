@echo off
setlocal
cd /d "%~dp0"

echo RTMS Biometric App - Windows build
echo.

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create venv. Install Python 3 and try again.
        pause
        exit /b 1
    )
)

echo Activating venv and installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
)

tasklist /FI "IMAGENAME eq FingerprintApp.exe" 2>nul | find /I "FingerprintApp.exe" >nul && (
    echo Stopping running FingerprintApp.exe...
    taskkill /F /IM FingerprintApp.exe >nul 2>&1
    timeout /t 2 /nobreak >nul
)
if exist "dist\FingerprintApp.exe" del /F /Q "dist\FingerprintApp.exe" 2>nul

echo Building executable with PyInstaller...
pyinstaller --noconfirm fingerprint_app.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

if exist "dist\app_settings.json" del /F /Q "dist\app_settings.json" >nul 2>&1
copy /Y "app_settings.json" "dist\app_settings.json" >nul

echo.
echo Done: dist\FingerprintApp.exe
echo Copy dist\FingerprintApp.exe and dist\app_settings.json together when deploying.
pause
