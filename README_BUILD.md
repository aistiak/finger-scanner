# Building Fingerprint Registration System to EXE

## Prerequisites
1. Make sure you have Python and pip installed
2. Install required dependencies: `pip install -r requirements.txt`

## Build Options

### Option 1: Simple Build (Recommended)
Run the simple build script:
```bash
build.bat
```

### Option 2: Advanced Build (With all dependencies)
Run the advanced build script:
```bash
build_advanced.bat
```

### Option 3: Using Spec File (Custom configuration)
```bash
pip install pyinstaller
pyinstaller fingerprint_app.spec
```

## Manual Build Command
If you prefer to run the command manually:
```bash
pyinstaller --onefile --windowed --name "FingerprintApp" main.py
```

## Output
- The executable will be created in the `dist/` folder
- File name: `FingerprintApp.exe` or `FingerprintRegistrationSystem.exe`

## Important Notes
1. **Database**: The app will create `fingerprints-1.db` automatically
2. **Settings**: Settings are saved to `app_settings.json`
3. **Dependencies**: Make sure ZKFP2 drivers are installed on target machines
4. **Permissions**: Run as administrator if fingerprint device access is needed

## Troubleshooting
- If build fails, try installing dependencies individually
- For "module not found" errors, add the module to hiddenimports in the spec file
- For large file size, use `--exclude-module` to remove unused modules

## Distribution
The final EXE file is self-contained and can be distributed to other Windows machines.
Make sure the target machine has:
- ZKFP2 fingerprint device drivers
- Proper permissions for device access
