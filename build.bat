@echo off
echo Installing PyInstaller if not already installed...
pip install pyinstaller

REM Close existing exe so PyInstaller can overwrite it (avoids "Access is denied")
tasklist /FI "IMAGENAME eq FingerprintApp.exe" 2>nul | find /I "FingerprintApp.exe" >nul && (
    echo.
    echo FingerprintApp.exe is running. Stopping it so the build can replace the file...
    taskkill /F /IM FingerprintApp.exe >nul 2>&1
    timeout /t 2 /nobreak >nul
)
if exist "dist\FingerprintApp.exe" (
    del /F /Q "dist\FingerprintApp.exe" 2>nul || (
        echo.
        echo Could not remove dist\FingerprintApp.exe - close any program using it then press any key.
        pause >nul
    )
)

echo Building Fingerprint Registration System...
pyinstaller --noconfirm fingerprint_app.spec

echo Build complete! Check the 'dist' folder for FingerprintApp.exe
pause
