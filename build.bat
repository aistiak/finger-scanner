@echo off
echo Installing PyInstaller if not already installed...
pip install pyinstaller

echo Building Fingerprint Registration System...
pyinstaller --onefile --windowed --name "FingerprintApp" --icon=icon.ico main.py

echo Build complete! Check the 'dist' folder for FingerprintApp.exe
pause
