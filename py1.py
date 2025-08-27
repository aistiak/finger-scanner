from pyzkfp import ZKFP2

# Initialize ZKFP2
zkfp2 = ZKFP2()
zkfp2.Init()

# Get device count and open the first device
device_count = zkfp2.GetDeviceCount()
print(f"{device_count} devices found")
zkfp2.OpenDevice(0)  # Connect to the first device

# Capture a fingerprint
while True:
    capture = zkfp2.AcquireFingerprint()
    if capture:
        tmp, img = capture
        print("Fingerprint captured")
        break

# Register a fingerprint (capture 3 samples and merge)
templates = []
for i in range(3):
    while True:
        capture = zkfp2.AcquireFingerprint()
        if capture:
            print(f"Fingerprint {i+1} captured")
            tmp, img = capture
            templates.append(tmp)
            break

# Merge templates and store in device
reg_temp, reg_temp_len = zkfp2.DBMerge(*templates)
print(reg_temp)
finger_id = 1  # Unique ID for the fingerprint
zkfp2.DBAdd(finger_id, reg_temp)

# Display fingerprint image (requires Pillow)
zkfp2.show_image(img)

# Terminate the device
zkfp2.Terminate()