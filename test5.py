from pyzkfp import ZKFP2
import io
import os

# Optional: Pillow for saving PNGs
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

def try_get_param(zk, code):
    """Safely query a device parameter (e.g., width/height)."""
    try:
        return zk.GetParameters(code)
    except Exception:
        return None

# Initialize ZKFP2
zkfp2 = ZKFP2()
ret = zkfp2.Init()
if ret != 0:
    raise RuntimeError(f"ZKFP2.Init() failed: {ret}")

# (Recommended) Initialize SDK DB engine (used by DBMerge/DBMatch)
try:
    ret = zkfp2.DBInit()
    if ret != 0:
        raise RuntimeError(f"ZKFP2.DBInit() failed: {ret}")
except Exception:
    # Some wrappers don’t expose DBInit; continue if yours doesn’t
    pass

# Get device count and open the first device
device_count = zkfp2.GetDeviceCount()
print(f"{device_count} devices found")
if device_count <= 0:
    zkfp2.Terminate()
    raise RuntimeError("No fingerprint devices found")

ret = zkfp2.OpenDevice(0)  # Connect to the first device
if ret != 0:
    zkfp2.Terminate()
    raise RuntimeError(f"OpenDevice(0) failed: {ret}")

# Capture a fingerprint (first image)
while True:
    capture = zkfp2.AcquireFingerprint()
    if capture:
        # Some wrappers return (template, image) or (ret, template, image)
        if isinstance(capture, tuple) and len(capture) == 2:
            tmp, img = capture
        elif isinstance(capture, tuple) and len(capture) == 3:
            r, tmp, img = capture
            if r != 0:
                continue
        else:
            continue
        print("Fingerprint captured")
        break

# Register a fingerprint (capture 3 samples and merge)
templates = [tmp]  # keep the first one
for i in range(2):  # need 2 more samples (total 3)
    while True:
        capture = zkfp2.AcquireFingerprint()
        if capture:
            if isinstance(capture, tuple) and len(capture) == 2:
                t, im = capture
            elif isinstance(capture, tuple) and len(capture) == 3:
                r, t, im = capture
                if r != 0:
                    continue
            else:
                continue
            print(f"Fingerprint {i+2} captured")
            templates.append(t)
            # keep updating img so we have a reasonably fresh image
            img = im if im else img
            break

# Merge templates
merged = zkfp2.DBMerge(templates[0], templates[1], templates[2])
if isinstance(merged, tuple):
    if len(merged) == 2:
        reg_temp, reg_temp_len = merged
    elif len(merged) == 3:
        r, reg_temp, reg_temp_len = merged
        if r != 0:
            raise RuntimeError(f"DBMerge failed: {r}")
    else:
        raise RuntimeError("Unexpected DBMerge return shape")
else:
    reg_temp = merged
    reg_temp_len = len(merged) if merged is not None else 0

if not reg_temp or reg_temp_len <= 0:
    raise RuntimeError("DBMerge produced empty template")

# Optionally store in SDK's in-memory DB (not required for file save)
try:
    finger_id = 1
    zkfp2.DBAdd(finger_id, reg_temp)
except Exception:
    pass

# --- Save template to file ---
TEMPLATE_PATH = "finger_template.bin"
with open(TEMPLATE_PATH, "wb") as f:
    f.write(reg_temp)
print(f"Saved merged template: {TEMPLATE_PATH} ({reg_temp_len} bytes)")

# --- Save image to file ---
# Try to get width/height; many SDKs expose them via GetParameters codes.
# Common codes vary by wrapper; these are typical examples:
#   1 => width, 2 => height  (your SDK may differ; adjust if needed)
width = try_get_param(zkfp2, 1)
height = try_get_param(zkfp2, 2)

# Normalize img to bytes
if isinstance(img, (bytes, bytearray, memoryview)):
    img_bytes = bytes(img)
else:
    # If the SDK returns some other type, try Pillow conversion (rare)
    if PIL_AVAILABLE and hasattr(img, "save"):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        width = height = None  # we already produced a PNG; don’t try frombytes below
    else:
        # last resort: try bytes(); if it fails, raise
        img_bytes = bytes(img)

IMAGE_RAW_PATH = "finger_image.raw"     # fallback raw bytes
IMAGE_PNG_PATH = "finger_image.png"     # preferred if we know dimensions
IMAGE_BMP_PATH = "finger_image.bmp"     # alternate if you want BMP

saved_png = False
if PIL_AVAILABLE and width and height:
    try:
        # Most devices output 8-bit grayscale (mode 'L')
        pil_img = Image.frombytes('L', (int(width), int(height)), img_bytes)
        pil_img.save(IMAGE_PNG_PATH)
        print(f"Saved fingerprint image: {IMAGE_PNG_PATH} ({int(width)}x{int(height)})")
        saved_png = True
    except Exception as e:
        print(f"PNG save failed ({e}); will save raw bytes instead.")

if not saved_png:
    # Save raw bytes (you can post-process later if needed)
    with open(IMAGE_RAW_PATH, "wb") as f:
        f.write(img_bytes)
    print(f"Saved fingerprint raw bytes: {IMAGE_RAW_PATH} (len={len(img_bytes)})")

# Display fingerprint image if your wrapper supports it (optional)
if hasattr(zkfp2, "show_image"):
    try:
        zkfp2.show_image(img)
    except Exception:
        pass

# Terminate the device/sdk cleanly
try:
    zkfp2.CloseDevice()
except Exception:
    pass
try:
    zkfp2.DBFree()
except Exception:
    pass
zkfp2.Terminate()
print("Device terminated")
