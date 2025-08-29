# -*- mode: python ; coding: utf-8 -*-
import os
import site

block_cipher = None

# Find pyzkfp package location
pyzkfp_path = None
for path in site.getsitepackages():
    potential_path = os.path.join(path, 'pyzkfp')
    if os.path.exists(potential_path):
        pyzkfp_path = potential_path
        break

# Collect ZKFP2 native libraries
zkfp_binaries = []
if pyzkfp_path:
    for file in os.listdir(pyzkfp_path):
        if file.endswith(('.dll', '.so', '.dylib')):
            zkfp_binaries.append((os.path.join(pyzkfp_path, file), '.'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=zkfp_binaries,
    datas=[
        ('app_settings.json', '.'),
        ('fingerprints-1.db', '.'),
        ('../py3.py', '.'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'requests',
        'pyzkfp',
        'pyzkfp.zkfp',
        'json',
        'base64',
        'threading',
        'datetime',
        'sqlite3',
        'os',
        'sys',
        'ctypes',
        'ctypes.wintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FingerprintRegistrationSystem',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
