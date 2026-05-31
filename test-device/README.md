# Test device (ZKTeco SLK20R)

Standalone script to verify the fingerprint scanner, USB driver, and `pyzkfp` SDK on **Windows x64**.

## Prerequisites

1. **Windows x64** (Intel/AMD) — not Windows on ARM. See [../SLK20R_ARM64_DRIVER.md](../SLK20R_ARM64_DRIVER.md) if Device Manager shows a yellow warning on ARM VMs.
2. **SLK20R** connected via USB (in a VM, pass the device through to Windows).
3. **ZKFinger SDK** installed as Administrator (provides the libusb-win32 driver).
4. **Device Manager** → SLK20R → Status **OK** (no error 28).

## Setup

From this folder:

```powershell
cd test-device
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Use the repo venv instead

If the project root already has `.venv-x64`:

```powershell
cd test-device
..\.venv-x64\Scripts\python.exe test_device.py
```

Use **x64** Python only. ARM64 Python will not work with this driver.

## Run tests

**Basic test** — environment, USB/PnP, SDK init, open device:

```powershell
python test_device.py
```

**With capture** — place a finger when prompted; waits up to 30 seconds by default:

```powershell
python test_device.py --capture
python test_device.py --capture --timeout 60
```

## What the script checks

| Step | What it verifies |
|------|------------------|
| Environment | Python PE arch, Windows OS arch, `libusb0.sys` present |
| USB / PnP | ZKTeco device (VID_1B55), Device Manager status |
| SDK | `pyzkfp` `Init()`, device count ≥ 1 |
| Device | `OpenDevice(0)` |
| Capture (optional) | `AcquireFingerprint()` returns template (and image if available) |

## Expected success output

```
=== Environment ===
...
Init(): OK — 1 device(s)

OpenDevice(0): OK

All tests passed.
```

With `--capture`, you should also see `AcquireFingerprint(): OK`.

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| No device on USB (VID_1B55) | Plug in scanner; in Parallels: **Devices → USB → SLK20R → Connect to Windows** |
| `libusb0.sys`: NOT installed | Reinstall ZKFinger SDK as Administrator on **x64** Windows |
| `Init()` or `OpenDevice` fails | Fix SLK20R in Device Manager first; reconnect USB |
| `AlgorithmLibraryInitializationError` | Scanner not visible to SDK — driver or USB passthrough |
| `CaptureLibraryInitializationError` | Broken or missing SLK20R driver |
| ARM Windows / ARM64 Python | Switch to x64 Windows VM and x64 Python — see [../SLK20R_ARM64_DRIVER.md](../SLK20R_ARM64_DRIVER.md) |

Quick checks on x64 Windows:

```powershell
Test-Path C:\Windows\System32\drivers\libusb0.sys
Get-PnpDevice | Where-Object InstanceId -match 'VID_1B55'
```

## Files

- `requirements.txt` — `pyzkfp` dependency
- `test_device.py` — diagnostic and optional capture test
