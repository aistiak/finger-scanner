"""
Fingerprint scanner worker processes and image helpers.
Separate module so multiprocessing spawn (PyInstaller exe) can import workers by name.
"""
import base64
import io

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_FINGER_RAW_DIMENSIONS = ((256, 288), (256, 360), (300, 400))


def _normalize_capture(capture):
    """Return (template, image_bytes) from AcquireFingerprint() result."""
    if not capture or not isinstance(capture, tuple):
        return None, None
    if len(capture) == 2:
        template, image = capture
    elif len(capture) == 3:
        ret, template, image = capture
        if ret != 0:
            return None, None
    else:
        return None, None
    if image is not None and not isinstance(image, (bytes, bytearray, memoryview)):
        try:
            image = bytes(image)
        except Exception:
            image = None
    elif image is not None:
        image = bytes(image)
    return template, image


def _encode_finger_image_b64(img_bytes, zkfp2=None):
    """Encode scanner image bytes as base64 PNG when possible, else raw base64."""
    if not img_bytes:
        return None
    if isinstance(img_bytes, (bytearray, memoryview)):
        img_bytes = bytes(img_bytes)
    if HAS_PIL:
        width = height = None
        if zkfp2 is not None:
            try:
                w = zkfp2.GetParameters(1)
                h = zkfp2.GetParameters(2)
                if w and h:
                    width, height = int(w), int(h)
            except Exception:
                pass
        if not width or not height:
            for w, h in _FINGER_RAW_DIMENSIONS:
                if len(img_bytes) == w * h:
                    width, height = w, h
                    break
        if width and height and len(img_bytes) >= width * height:
            try:
                pil = Image.frombytes("L", (width, height), img_bytes[: width * height])
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception:
                pass
        try:
            Image.open(io.BytesIO(img_bytes))
            return base64.b64encode(img_bytes).decode("utf-8")
        except Exception:
            pass
    return base64.b64encode(img_bytes).decode("utf-8")


def decode_finger_image_bytes(raw_bytes):
    """Decode stored finger image bytes for display (PNG/JPEG or raw grayscale)."""
    if not raw_bytes:
        return None
    if HAS_PIL:
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            img.load()
            return raw_bytes
        except Exception:
            pass
        for width, height in _FINGER_RAW_DIMENSIONS:
            if len(raw_bytes) == width * height:
                try:
                    img = Image.frombytes("L", (width, height), raw_bytes)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return buf.getvalue()
                except Exception:
                    continue
    return None


def _as_int(value, default=0):
    """Convert pythonnet / SDK numeric returns (incl. IntPtr) to int safely."""
    if value is None or value is False:
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return value.ToInt64()
    except Exception:
        pass
    return default


def _setup_zkfp(zkfp2, progress_queue=None):
    """Initialize SDK + in-memory DB + device (required before DBMatch)."""
    def say(msg):
        if progress_queue is not None:
            progress_queue.put(msg)

    say("Initializing fingerprint SDK...")
    zkfp2.Init()
    try:
        zkfp2.DBInit()
    except Exception:
        pass
    say("Opening device...")
    zkfp2.OpenDevice(0)


def _template_for_match(raw):
    """Convert stored/live template bytes to a type pyzkfp DBMatch accepts."""
    if raw is None:
        return None
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        return raw
    data = bytes(raw)
    try:
        from System import Array, Byte
        try:
            return Array[Byte](data)
        except Exception:
            return Array[Byte](list(data))
    except Exception:
        return data


def _db_match_templates(zkfp2, stored, live):
    """Compare stored vs live merged templates. Returns match score."""
    stored_t = _template_for_match(stored)
    live_t = _template_for_match(live)
    if stored_t is None or live_t is None:
        return 0
    try:
        return _as_int(zkfp2.DBMatch(stored_t, live_t), 0)
    except Exception:
        return 0


def _registration_worker_process(progress_queue, result_queue):
    """
    Run in a separate process so device handles are fully released when process exits.
    result_queue: ('ok', (template_b64, finger_image_b64)) or ('error', message).
    """
    try:
        from pyzkfp import ZKFP2
        progress_queue.put("Initializing fingerprint device...")
        zkfp2 = ZKFP2()
        zkfp2.Init()
        progress_queue.put("Opening device...")
        zkfp2.OpenDevice(0)
        progress_queue.put("Device connected successfully")
        templates = []
        finger_image = None
        for i in range(3):
            progress_queue.put(f"Place finger {i + 1}/3 - Waiting for finger on scanner...")
            while True:
                capture = zkfp2.AcquireFingerprint()
                template, image = _normalize_capture(capture)
                if template:
                    templates.append(template)
                    if i == 0 and image:
                        finger_image = image
                    progress_queue.put(f"Finger {i + 1}/3 captured. Please lift your finger.")
                    break
        progress_queue.put("Processing fingerprint template...")
        reg_temp, _ = zkfp2.DBMerge(*templates)
        template_b64 = base64.b64encode(bytes(reg_temp)).decode("utf-8")
        finger_image_b64 = _encode_finger_image_b64(finger_image, zkfp2)
        try:
            zkfp2.Terminate()
        except Exception:
            pass
        result_queue.put(("ok", (template_b64, finger_image_b64)))
    except Exception as e:
        result_queue.put(("error", str(e)))


def _capture_worker_process(progress_queue, result_queue):
    """
    Capture a single fingerprint template.
    result_queue: ('ok', template_b64) or ('error', message).
    """
    zkfp2 = None
    try:
        from pyzkfp import ZKFP2
        zkfp2 = ZKFP2()
        _setup_zkfp(zkfp2, progress_queue)
        progress_queue.put("Place finger on scanner...")
        live_template = None
        while True:
            capture = zkfp2.AcquireFingerprint()
            template, _ = _normalize_capture(capture)
            if template:
                live_template = template
                progress_queue.put("Fingerprint captured.")
                break
        template_b64 = base64.b64encode(bytes(live_template)).decode("utf-8")
        result_queue.put(("ok", template_b64))
    except Exception as e:
        result_queue.put(("error", str(e)))
    finally:
        if zkfp2 is not None:
            try:
                zkfp2.Terminate()
            except Exception:
                pass


def _match_worker_process(progress_queue, result_queue, stored_template_b64):
    """
    Run in a separate process so device handles are fully released when process exits.
    result_queue: ('ok', True/False) or ('error', message).
    """
    try:
        from pyzkfp import ZKFP2
        stored_template = base64.b64decode(stored_template_b64)
        progress_queue.put("Initializing fingerprint device...")
        zkfp2 = ZKFP2()
        _setup_zkfp(zkfp2, progress_queue)
        progress_queue.put("Device connected successfully")
        progress_queue.put("Place finger on scanner...")
        live_template = None
        while True:
            capture = zkfp2.AcquireFingerprint()
            template, _ = _normalize_capture(capture)
            if template:
                live_template = template
                progress_queue.put("Fingerprint captured. Comparing...")
                break
        match_result = _db_match_templates(zkfp2, stored_template, live_template)
        try:
            zkfp2.Terminate()
        except Exception:
            pass
        result_queue.put(("ok", match_result > 0))
    except Exception as e:
        result_queue.put(("error", str(e)))


def _sequential_match_worker_process(progress_queue, result_queue, live_template_b64, records):
    """Compare live template against a batch; return best-scoring record on this page."""
    zkfp2 = None
    try:
        from pyzkfp import ZKFP2
        live_template = base64.b64decode(live_template_b64)
        zkfp2 = ZKFP2()
        _setup_zkfp(zkfp2, progress_queue)
        total = len(records)
        best_score = 0
        best_record = None
        for index, record in enumerate(records, start=1):
            progress_queue.put(f"Comparing {index}/{total} on this page...")
            template_b64 = record.get("template")
            if not template_b64:
                continue
            try:
                stored_template = base64.b64decode(template_b64)
            except Exception:
                continue
            score = _db_match_templates(zkfp2, stored_template, live_template)
            if score > best_score:
                best_score = score
                best_record = record
        result_queue.put(("ok", {"record": best_record, "score": best_score}))
    except Exception as e:
        result_queue.put(("error", str(e)))
    finally:
        if zkfp2 is not None:
            try:
                zkfp2.Terminate()
            except Exception:
                pass
