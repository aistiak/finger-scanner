@echo off
echo Installing PyInstaller if not already installed...
pip install pyinstaller

echo Building Fingerprint Registration System with ZKFP2 native libraries...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "FingerprintRegistrationSystem" ^
    --add-data "app_settings.json;." ^
    --add-data "fingerprints-1.db;." ^
    --add-binary "%VIRTUAL_ENV%\Lib\site-packages\pyzkfp\*.dll;." ^
    --hidden-import "tkinter" ^
    --hidden-import "tkinter.ttk" ^
    --hidden-import "requests" ^
    --hidden-import "pyzkfp" ^
    --hidden-import "pyzkfp.zkfp" ^
    --hidden-import "json" ^
    --hidden-import "base64" ^
    --hidden-import "threading" ^
    --hidden-import "datetime" ^
    --hidden-import "sqlite3" ^
    --hidden-import "ctypes" ^
    --hidden-import "ctypes.wintypes" ^
    --collect-all "pyzkfp" ^
    --collect-all "tkinter" ^
    main.py

echo Build complete! Check the 'dist' folder for FingerprintRegistrationSystem.exe
echo.
echo Note: Make sure the fingerprint device drivers are installed on target machines
pause
