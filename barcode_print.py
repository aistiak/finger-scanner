"""Code128 barcode generation and A4 label printing for phlebotomist workflows."""
import os
import sys
import tempfile
import threading
import time
from io import BytesIO

try:
    from barcode import Code128
    from barcode.writer import ImageWriter

    HAS_BARCODE = True
except ImportError:
    HAS_BARCODE = False

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# ~90mm wide barcode block — readable Code128, not page-filling.
BARCODE_WIDTH_MM = 90


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


def _render_code128_image(serial):
    """Render Code128 (+ human-readable text) to a PIL RGB image."""
    buffer = BytesIO()
    options = {
        "module_width": 0.4,
        "module_height": 18.0,
        "quiet_zone": 3.0,
        "font_size": 14,
        "text_distance": 5.0,
        "write_text": True,
        "dpi": 300,
    }
    Code128(serial, writer=ImageWriter()).write(buffer, options=options)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def generate_barcode_a4_pdf(serial):
    """
    Generate a real A4 PDF with a reasonably sized Code128 barcode centered
    horizontally and vertically (middle of the page).

    Returns path to a temporary .pdf file that prints/saves correctly
    (including Microsoft Print to PDF / Save as PDF).
    """
    serial = (serial or "").strip()
    if not serial:
        raise ValueError("No printable serial provided")
    if not HAS_BARCODE:
        raise RuntimeError("python-barcode is not installed")
    if not HAS_PIL:
        raise RuntimeError("Pillow is not installed")
    if not HAS_REPORTLAB:
        raise RuntimeError("reportlab is not installed")

    barcode_img = _render_code128_image(serial)

    fd_png, png_path = tempfile.mkstemp(prefix="rtms_barcode_img_", suffix=".png")
    os.close(fd_png)
    fd_pdf, pdf_path = tempfile.mkstemp(prefix="rtms_barcode_", suffix=".pdf")
    os.close(fd_pdf)

    try:
        barcode_img.save(png_path, "PNG")

        page_w, page_h = A4
        draw_w = BARCODE_WIDTH_MM * mm
        aspect = barcode_img.height / float(barcode_img.width)
        draw_h = draw_w * aspect
        # Cap height so tall serials stay compact (~40mm max).
        max_h = 40 * mm
        if draw_h > max_h:
            draw_h = max_h
            draw_w = draw_h / aspect

        x = (page_w - draw_w) / 2.0
        y = (page_h - draw_h) / 2.0

        c = pdf_canvas.Canvas(pdf_path, pagesize=A4)
        c.setTitle(f"Barcode {serial}")
        c.drawImage(
            png_path,
            x,
            y,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask="auto",
        )
        c.showPage()
        c.save()
    finally:
        try:
            os.unlink(png_path)
        except OSError:
            pass

    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 200:
        raise RuntimeError("Barcode PDF was not created correctly")
    return pdf_path


def generate_barcode_label_png(serial):
    """Generate a preview PNG of the A4 layout (barcode centered)."""
    serial = (serial or "").strip()
    if not serial:
        raise ValueError("No printable serial provided")
    if not HAS_BARCODE or not HAS_PIL:
        raise RuntimeError("Barcode dependencies are not installed")

    # Rasterize a simple A4 preview at 150 DPI for debugging/preview.
    dpi = 150
    page_w = int(8.27 * dpi)
    page_h = int(11.69 * dpi)
    barcode_img = _render_code128_image(serial)
    target_w = int((BARCODE_WIDTH_MM / 25.4) * dpi)
    ratio = target_w / float(barcode_img.width)
    target_h = max(1, int(round(barcode_img.height * ratio)))
    max_h = int((40 / 25.4) * dpi)
    if target_h > max_h:
        ratio = max_h / float(target_h)
        target_w = max(1, int(round(target_w * ratio)))
        target_h = max_h
    fitted = barcode_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    page = Image.new("RGB", (page_w, page_h), "white")
    page.paste(fitted, ((page_w - target_w) // 2, (page_h - target_h) // 2))

    fd, path = tempfile.mkstemp(prefix="rtms_barcode_", suffix=".png")
    os.close(fd)
    page.save(path, "PNG")
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
        return True


def _print_file_windows(path, show_dialog=False):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    if show_dialog:
        # Open the A4 PDF so the user can Print / Save as PDF from the viewer.
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
            raise RuntimeError("Could not open barcode document for printing.")
        return "opened"
    rc = os.system(f'lpr "{path}"')
    if rc != 0:
        raise RuntimeError("lpr failed; open the PDF and print manually.")
    return "printed"


def print_barcode_label(serial, prefer_silent=True):
    """
    Generate a centered A4 Code128 PDF and print it.

    Returns (ok, status, detail) where status is printed|opened|error.
    Prefers silent print to the default printer; falls back to opening the
    PDF so the user can use the system print UI / Save as PDF.
    """
    serial = (serial or "").strip()
    if not serial:
        return False, "error", "No printable serial available for this patient."

    try:
        path = generate_barcode_a4_pdf(serial)
    except Exception as e:
        return False, "error", f"Failed to generate barcode: {e}"

    def cleanup_later(p):
        # Keep the file long enough for print spooler / Save as PDF.
        time.sleep(180)
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
                        f"Opened A4 barcode PDF for {serial}.",
                    )
                except Exception as dialog_err:
                    return False, "error", str(dialog_err)
        else:
            if sys.platform == "win32":
                result = _print_file_windows(path, show_dialog=True)
            else:
                result = _print_file_posix(path, show_dialog=True)
            return True, result, f"Opened A4 barcode PDF for {serial}"
    finally:
        threading.Thread(target=cleanup_later, args=(path,), daemon=True).start()


def print_barcode_async(serial, prefer_silent=True, on_done=None):
    """Print on a background thread; call on_done(ok, status, detail) when finished."""

    def worker():
        ok, status, detail = print_barcode_label(serial, prefer_silent=prefer_silent)
        if on_done:
            on_done(ok, status, detail)

    threading.Thread(target=worker, daemon=True).start()
