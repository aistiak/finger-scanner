"""Code128 barcode generation and label printing for phlebotomist workflows."""
import os
import sys
import tempfile
import threading
import time

try:
    from barcode import Code128
    from barcode.writer import ImageWriter

    HAS_BARCODE = True
except ImportError:
    HAS_BARCODE = False

try:
    import PIL  # noqa: F401 — ImageWriter requires Pillow

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def resolve_printable_serial(user_data):
    """
    Resolve the barcode payload string from a patient/API payload.

    Prefer API `registration_id` (printable daily serial), then `daily_serial_no`,
    then nested `service_request` fields.
    """
    if not isinstance(user_data, dict):
        return None
    id_keys = ("registration_id", "daily_serial_no", "registration_number")
    sources = (
        user_data,
        user_data.get("fingerprint") or {},
        user_data.get("service_request") or {},
    )
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in id_keys:
            value = source.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def generate_barcode_label_png(serial):
    """
    Generate a compact Code128 label PNG with human-readable serial text.
    Returns path to a temporary PNG file.
    """
    serial = (serial or "").strip()
    if not serial:
        raise ValueError("No printable serial provided")
    if not HAS_BARCODE:
        raise RuntimeError("python-barcode is not installed")
    if not HAS_PIL:
        raise RuntimeError("Pillow is not installed")

    fd, tmp_path = tempfile.mkstemp(prefix="rtms_barcode_", suffix=".png")
    os.close(fd)
    base = tmp_path[:-4]  # ImageWriter.save appends .png
    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    options = {
        "module_width": 0.35,
        "module_height": 14.0,
        "quiet_zone": 2.5,
        "font_size": 12,
        "text_distance": 4.0,
        "write_text": True,
        "dpi": 300,
    }
    Code128(serial, writer=ImageWriter()).save(base, options=options)
    path = base + ".png"
    if not os.path.exists(path):
        raise RuntimeError("Barcode image was not created")
    return path


def _windows_has_printer():
    if sys.platform != "win32":
        return False
    try:
        import win32print  # type: ignore

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = win32print.EnumPrinters(flags)
        return bool(printers)
    except Exception:
        # Assume a printer may exist; startfile will surface errors.
        return True


def _print_file_windows(path, show_dialog=False):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    if show_dialog:
        # Open the label so the user can use the OS print UI / choose a printer.
        os.startfile(path)
        return "opened"

    if not _windows_has_printer():
        raise RuntimeError("No printer is available. Connect a printer and try again.")

    try:
        os.startfile(path, "print")
        return "printed"
    except OSError as e:
        raise RuntimeError(f"Could not print to default printer: {e}") from e


def _print_file_posix(path, show_dialog=False):
    path = os.path.abspath(path)
    if show_dialog or sys.platform == "darwin":
        if sys.platform == "darwin":
            rc = os.system(f'open "{path}"')
        else:
            rc = os.system(f'xdg-open "{path}"')
        if rc != 0:
            raise RuntimeError("Could not open barcode label for printing.")
        return "opened"
    rc = os.system(f'lpr "{path}"')
    if rc != 0:
        raise RuntimeError("lpr failed; open the label and print manually.")
    return "printed"


def print_barcode_label(serial, prefer_silent=True):
    """
    Generate a Code128 label and print it.

    Returns (ok, status, detail) where status is printed|opened|error.
    Prefers silent print to the default printer; falls back to opening the
    label so the user can use the system print UI.
    """
    serial = (serial or "").strip()
    if not serial:
        return False, "error", "No printable serial available for this patient."

    try:
        path = generate_barcode_label_png(serial)
    except Exception as e:
        return False, "error", f"Failed to generate barcode: {e}"

    def cleanup_later(p):
        time.sleep(45)
        try:
            os.unlink(p)
        except OSError:
            pass

    try:
        if prefer_silent:
            try:
                if sys.platform == "win32":
                    result = _print_file_windows(path, show_dialog=False)
                else:
                    result = _print_file_posix(path, show_dialog=False)
                return True, result, f"Barcode sent to printer ({serial})"
            except Exception as silent_err:
                try:
                    if sys.platform == "win32":
                        result = _print_file_windows(path, show_dialog=True)
                    else:
                        result = _print_file_posix(path, show_dialog=True)
                    return (
                        True,
                        result,
                        f"Default print unavailable ({silent_err}). "
                        f"Opened printer interface for {serial}.",
                    )
                except Exception as dialog_err:
                    return False, "error", str(dialog_err)
        else:
            if sys.platform == "win32":
                result = _print_file_windows(path, show_dialog=True)
            else:
                result = _print_file_posix(path, show_dialog=True)
            return True, result, f"Opened printer interface for {serial}"
    finally:
        threading.Thread(target=cleanup_later, args=(path,), daemon=True).start()


def print_barcode_async(serial, prefer_silent=True, on_done=None):
    """Print on a background thread; call on_done(ok, status, detail) when finished."""

    def worker():
        ok, status, detail = print_barcode_label(serial, prefer_silent=prefer_silent)
        if on_done:
            on_done(ok, status, detail)

    threading.Thread(target=worker, daemon=True).start()
