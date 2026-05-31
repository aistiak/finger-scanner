"""Standalone ZKTeco SLK20R device test. See README.md for setup and usage."""
from __future__ import annotations

import argparse
import json
import os
import platform
import struct
import subprocess
import sys
import time


def _pe_arch(exe: str) -> str:
    with open(exe, "rb") as f:
        f.seek(0x3C)
        pe = struct.unpack("<I", f.read(4))[0]
        f.seek(pe + 4)
        machine = struct.unpack("<H", f.read(2))[0]
    return {0x8664: "x64", 0x14C: "x86", 0xAA64: "ARM64"}.get(machine, hex(machine))


def _os_arch() -> str:
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_OperatingSystem).OSArchitecture",
            ],
            text=True,
            errors="replace",
        ).strip()
        return out
    except Exception:
        return "unknown"


def _libusb_driver_installed() -> bool:
    return os.path.isfile(r"C:\Windows\System32\drivers\libusb0.sys")


def _check_pnp_device() -> str:
    try:
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
                "  Connect the SLK20R and pass USB through to this Windows VM."
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


def print_environment() -> None:
    print("=== Environment ===")
    print(f"Python: {sys.executable}")
    print(f"Python arch (PE): {_pe_arch(sys.executable)}")
    print(f"platform.machine(): {platform.machine()}")
    os_arch = _os_arch()
    print(f"Windows OS: {os_arch}")
    print(
        f"ZKTeco libusb driver (libusb0.sys): "
        f"{'installed' if _libusb_driver_installed() else 'NOT installed'}"
    )
    if "ARM" in os_arch.upper() and not _libusb_driver_installed():
        print(
            "\n*** Windows ARM64 — ZKTeco USB driver is not supported here ***\n"
            "  Use Windows x64 (Intel/AMD) with x64 Python. See SLK20R_ARM64_DRIVER.md.\n"
        )
    print()
    print("USB / PnP (ZKTeco VID_1B55):")
    print(_check_pnp_device())
    print()


def test_pyzkfp_init() -> tuple[object, int]:
    from pyzkfp import ZKFP2

    print("=== pyzkfp ===")
    z = ZKFP2()
    z.Init()
    count = z.GetDeviceCount()
    print(f"Init(): OK — {count} device(s)")
    if count < 1:
        z.Terminate()
        raise RuntimeError("No fingerprint devices reported by SDK")
    return z, count


def test_open_device(zk) -> None:
    zk.OpenDevice(0)
    print("OpenDevice(0): OK")


def test_capture(zk, timeout_sec: float = 30.0) -> None:
    print(f"=== Capture (place finger, timeout {timeout_sec:.0f}s) ===")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        capture = zk.AcquireFingerprint()
        if capture:
            template, image = capture[0], capture[1]
            print(f"AcquireFingerprint(): OK — template {len(template)} bytes")
            if image is not None:
                print(f"  image buffer: {len(image)} bytes")
            return
        time.sleep(0.05)
    raise TimeoutError("No fingerprint captured within timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ZKTeco fingerprint scanner")
    parser.add_argument(
        "--capture",
        action="store_true",
        help="After opening the device, wait for one fingerprint scan",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for a finger when --capture is used (default: 30)",
    )
    args = parser.parse_args()

    print_environment()

    zk = None
    try:
        zk, _ = test_pyzkfp_init()
        print()
        test_open_device(zk)
        if args.capture:
            print()
            test_capture(zk, timeout_sec=args.timeout)
        print()
        print("All tests passed.")
        return 0
    except Exception as e:
        print(f"\nFAILED — {type(e).__name__}: {e}")
        if _pe_arch(sys.executable) == "ARM64":
            print("Hint: use x64 Python on x64 Windows, not ARM64 Python.")
        print(
            "\nChecklist:\n"
            "  1. SLK20R connected and USB passed through to Windows\n"
            "  2. Device Manager → SLK20R shows Status OK\n"
            "  3. ZKFinger SDK installed (Administrator)\n"
            "  4. x64 Windows + x64 Python"
        )
        return 1
    finally:
        if zk is not None:
            try:
                zk.Terminate()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
