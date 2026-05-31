# SLK20R driver fix on Windows ARM64 (Parallels / Apple Silicon)

## Why Device Manager stays yellow

Your VM is **Windows ARM64** (`ARM 64-bit Processor`). The ZKTeco SLK20R driver shipped with ZKFinger SDK is **libusb-win32** (`zkusbdevices.inf`, dated 2017). It only includes:

- x86 (`libusb0.sys`)
- x64 (`libusb0_x64.sys`)

There is **no ARM64 `.sys` driver**. Windows ARM cannot load x64 kernel USB drivers for this device. Reinstalling the SDK as Administrator will not change that.

Evidence on this machine:

| Check | Result |
|-------|--------|
| SLK20R in Device Manager | Error 28 — driver failed to install |
| `C:\Windows\System32\drivers\libusb0.sys` | **Missing** |
| `oem9.inf` (ZKTeco) | Has `NTAMD64` sections only — no `NTARM64` |

## What to do

### Option A — Recommended: x64 Windows VM (Parallels)

1. In Parallels, create or switch to **Windows 11 64-bit (x64 / Intel/AMD emulation)**, not Windows on ARM.
2. Pass the SLK20R USB device to that x64 VM.
3. Install ZKFinger SDK **inside the x64 VM** (as Administrator).
4. Device Manager should show **SLK20R → OK**.
5. Use x64 Python there:
   ```powershell
   .\.venv-x64\Scripts\python.exe check_scanner.py
   .\.venv-x64\Scripts\python.exe main.py
   ```

### Option B — Native x64 PC

Use any Intel/AMD Windows 10/11 machine, install SDK + app there.

### Option C — Does NOT work

- Re-running the same SDK installer on **this ARM Windows VM**
- Using Zadig / WinUSB (ZKTeco SDK expects their libusb-win32 filter driver)
- Using ARM64 Python or ARM64 `.venv` from `uv venv`

## Verify after switching to x64 Windows

```powershell
# libusb kernel driver should exist
Test-Path C:\Windows\System32\drivers\libusb0.sys   # True

# Scanner should be OK
Get-PnpDevice | Where-Object InstanceId -match 'VID_1B55'

# pyzkfp should init
.\.venv-x64\Scripts\python.exe check_scanner.py
```

Expected: `pyzkfp Init(): OK — 1 device(s)`
