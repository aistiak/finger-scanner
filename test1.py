from pyzkfp import ZKFP2

# Initialize the device
zkfp2 = ZKFP2()
zkfp2.Init()

# Get device count and open the first device
device_count = zkfp2.GetDeviceCount()
print(f"{device_count} devices found")
zkfp2.OpenDevice(0)

# --- ENROLL FINGERPRINT ---
print("Place your finger on the scanner for enrollment...")
templates = []
for i in range(3):
    print(f"Capture {i+1} of 3...")
    while True:
        capture = zkfp2.AcquireFingerprint()
        if capture:
            tmp, img = capture
            templates.append(tmp)
            break
        # Optional: Add a delay here to prevent high CPU usage

# Merge the three captured templates into one final template
regTemp, regTempLen = zkfp2.DBMerge(*templates)

# Store the final template in your database (example: a simple dictionary)
finger_database = {}
user_id = 1
finger_database[user_id] = regTemp
print(f"Fingerprint enrolled for User ID: {user_id}")

print('finger_database[user_id]')
print(str(finger_database[user_id]))
# --- MATCH FINGERPRINT ---
print("\nPlace your finger on the scanner for verification...")
while True:
    capture = zkfp2.AcquireFingerprint()
    if capture:
        tmp, img = capture
        # Perform 1:1 verification
        matched = zkfp2.DBMatch(tmp, finger_database[user_id])
        if matched:
            print("MATCH FOUND: Fingerprint verified for User ID 1.")
        else:
            print("NO MATCH: The fingerprint does not match the enrolled template.")
        break
    # Optional: Add a delay here

# Terminate the device
zkfp2.Terminate()
print("Device terminated.")