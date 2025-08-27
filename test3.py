from pyzkfp import ZKFP2
import sqlite3
import uuid


import base64

def bytes_to_base64_string(byte_data: bytes) -> str:
    """Converts a byte array to a Base64-encoded string."""
    encoded_bytes = base64.b64encode(byte_data)
    encoded_string = encoded_bytes.decode('utf-8')
    return encoded_string

def base64_string_to_bytes(base64_string: str) -> bytes:
    """Converts a Base64-encoded string back to a byte array."""
    decoded_bytes = base64.b64decode(base64_string)
    return decoded_bytes
# Initialize the device
zkfp2 = ZKFP2()
zkfp2.Init()

# Get device count and open the first device
device_count = zkfp2.GetDeviceCount()
print(f"{device_count} devices found")
zkfp2.OpenDevice(0)

# Connect to the database
conn = sqlite3.connect('test3.db')
cursor = conn.cursor()

# Create the fingerprints table if it does not exist
cursor.execute('CREATE TABLE IF NOT EXISTS fingerprints (id TEXT, template BLOB)')

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
reg_temp, reg_temp_len = zkfp2.DBMerge(*templates)
print('type(reg_temp)',type(reg_temp))
print('base64(reg_temp)',bytes_to_base64_string(reg_temp))
print(reg_temp)
# Generate a random ID and save to DB
user_id = str(uuid.uuid4())
cursor.execute('INSERT INTO fingerprints (id, template) VALUES (?, ?)', (user_id, str(reg_temp)))
conn.commit()
print(f"Fingerprint enrolled for User ID: {user_id}")

# --- MATCH FINGERPRINT ---
print("\nPlace your finger on the scanner for verification...")
while True:
    capture = zkfp2.AcquireFingerprint()
    if capture:
        tmp, img = capture
        # Perform 1:1 verification
        cursor.execute('SELECT template FROM fingerprints WHERE id = ?', (user_id,))
        db_template = cursor.fetchone()[0]
        matched = zkfp2.DBMatch(tmp, db_template)
        if matched:
            print("MATCH FOUND: Fingerprint verified for User ID 1.")
        else:
            print("NO MATCH: The fingerprint does not match the enrolled template.")
        break
    # Optional: Add a delay here

# Close the database connection
conn.close()

# Terminate the device
zkfp2.Terminate()
print("Device terminated.")