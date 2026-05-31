"""Diagnose ZKTeco fingerprint scanner and pyzkfp initialization."""
import os
import platform
import struct
import sys


def _pe_arch(exe: str) -> str:
    with open(exe, "rb") as f:
        f.seek(0x3C)
        pe = struct.unpack("<I", f.read(4))[0]
        f.seek(pe + 4)
        machine = struct.unpack("<H", f.read(2))[0]
    return {0x8664: "x64", 0x14C: "x86", 0xAA64: "ARM64"}.get(machine, hex(machine))


def _os_arch() -> str:
    try:
        import subprocess

        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).OSArchitecture"],
            text=True,
            errors="replace",
        ).strip()
        return out
    except Exception:
        return "unknown"


def _libusb_driver_installed() -> bool:
    return os.path.isfile(r"C:\Windows\System32\drivers\libusb0.sys")


def _check_pnp_device():
    try:
        import json
        import subprocess

        ps = (
            "Get-PnpDevice | "
            "Where-Object { $_.InstanceId -match 'VID_1B55' } | "
            "Select-Object FriendlyName, Status, Problem, Present, InstanceId | "
            "ConvertTo-Json -Compress"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            errors="replace",
        ).strip()
        if not out:
            return (
                "No ZKTeco scanner on USB (VID_1B55).\n"
                "  The SLK20R is not connected to this Windows VM.\n"
                "  In Parallels: Devices → USB → select SLK20R → Connect to Windows."
            )
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        lines = []
        for dev in data:
            lines.append(
                f"  {dev.get('FriendlyName')} — Status: {dev.get('Status')}, "
                f"Problem: {dev.get('Problem')}, Present: {dev.get('Present')}"
            )
            if dev.get("Status") != "OK":
                lines.append(
                    "  → Fix in Device Manager or reinstall ZKFinger SDK (as Admin)."
                )
        return "\n".join(lines)
    except Exception as e:
        return f"Could not query devices: {e}"


def main():
    print(f"Python: {sys.executable}")
    print(f"Python arch (PE): {_pe_arch(sys.executable)}")
    print(f"platform.machine(): {platform.machine()}")
    os_arch = _os_arch()
    print(f"Windows OS: {os_arch}")
    print(f"ZKTeco libusb driver (libusb0.sys): {'installed' if _libusb_driver_installed() else 'NOT installed'}")
    if "ARM" in os_arch.upper() and not _libusb_driver_installed():
        print(
            "\n*** Windows ARM64 detected — ZKTeco USB driver cannot install here ***\n"
            "  The SLK20R driver (zkusbdevices.inf / libusb-win32) only supports x86/x64 Windows.\n"
            "  There is no ARM64 kernel driver, so Device Manager stays yellow (error 28)\n"
            "  no matter how many times you run the SDK installer as Admin.\n"
            "\n  Fix options:\n"
            "  A) In Parallels: create/use Windows 11 **x64 (64-bit Intel/AMD)** VM, not ARM Windows\n"
            "  B) Run this app on a physical Intel/AMD Windows PC\n"
            "  C) Connect SLK20R directly to native x64 Windows (not this ARM VM)\n"
        )
    print()
    print("USB / PnP (ZKTeco VID_1B55):")
    print(_check_pnp_device())
    print()
    print("pyzkfp Init():")
    try:
        from pyzkfp import ZKFP2

        z = ZKFP2()
        z.Init()
        count = z.GetDeviceCount()
        print(f"  OK — {count} device(s)")
        z.Terminate()
    except Exception as e:
        err_name = type(e).__name__
        print(f"  FAILED — {err_name}: {e}")
        if err_name == "AlgorithmLibraryInitializationError":
            print(
                "\n  This usually means the SDK cannot see a working scanner.\n"
                "  ZKTeco requires the SLK20R to be connected before Init() succeeds."
            )
        elif err_name == "CaptureLibraryInitializationError":
            print(
                "\n  Capture driver failed — often a broken SLK20R driver in Device Manager."
            )
        if _pe_arch(sys.executable) == "ARM64":
            print(
                "\n  Hint: Use x64 Python (.venv-x64), not ARM64 .venv from uv venv."
            )
        print(
            "\n  Checklist:\n"
            "  1. Plug in SLK20R and connect USB to this Windows VM (Parallels passthrough)\n"
            "  2. Device Manager → SLK20R should show Status OK (no yellow !)\n"
            "  3. Run: .\\.venv-x64\\Scripts\\python.exe check_scanner.py"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
