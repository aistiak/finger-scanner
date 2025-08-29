@echo off
echo Installing PyInstaller if not already installed...
pip install pyinstaller

echo Finding pyzkfp DLL files...
python -c "import pyzkfp; import os; print('ZKFP Path:', os.path.dirname(pyzkfp.__file__))"

echo Building using spec file (recommended for ZKFP2 libraries)...
pyinstaller fingerprint_app.spec

if not exist "dist\FingerprintRegistrationSystem.exe" (
    echo Build failed! Trying alternative method...
    echo.
    echo Building with manual DLL inclusion...
    pyinstaller ^
        --onefile ^
        --windowed ^
        --name "FingerprintRegistrationSystem" ^
        --collect-all "pyzkfp" ^
        --copy-metadata "pyzkfp" ^
        --hidden-import "pyzkfp" ^
        --hidden-import "pyzkfp.zkfp" ^
        --hidden-import "ctypes" ^
        --hidden-import "ctypes.wintypes" ^
        main.py
)

echo.
echo Build complete! Check the 'dist' folder for FingerprintRegistrationSystem.exe
echo.
echo IMPORTANT: If the exe still fails to run:
echo 1. Copy libzkfpcsharp.dll manually to the same folder as the exe
echo 2. Install ZKFP2 SDK on the target machine
echo 3. Run as administrator for device access
pause
