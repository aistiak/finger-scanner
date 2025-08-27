from pyzkfp import ZKFP2

# # Initialize ZKFP2
zkfp2 = ZKFP2()
zkfp2.Init()

# # Get device count and open the first device
# device_count = zkfp2.GetDeviceCount()
# print(f"{device_count} devices found")
# zkfp2.OpenDevice(0)  # Connect to the first device

# # Capture a fingerprint
# while True:
#     capture = zkfp2.AcquireFingerprint()
#     if capture:
#         tmp, img = capture
#         print("Fingerprint captured")
#         break

# # Register a fingerprint (capture 3 samples and merge)
# templates = []
# for i in range(3):
#     while True:
#         capture = zkfp2.AcquireFingerprint()
#         if capture:
#             print(f"Fingerprint {i+1} captured")
#             tmp, img = capture
#             templates.append(tmp)
#             break

# # Merge templates and store in device
# reg_temp, reg_temp_len = zkfp2.DBMerge(*templates)
# finger_id = 1  # Unique ID for the fingerprint
# zkfp2.DBAdd(finger_id, reg_temp)

# # Display fingerprint image (requires Pillow)
# zkfp2.show_image(img)

# # Terminate the device
# zkfp2.Terminate()


import uuid
import sqlite3
import io

# # Save image to SQLite database
# conn = sqlite3.connect('fingerprints3.db')
# cursor = conn.cursor()

# cursor.execute('''
#     CREATE TABLE IF NOT EXISTS fingerprints (
#         id TEXT PRIMARY KEY,
#         image BLOB
#     )
# ''')

# user_id = str(uuid.uuid4())
# image_bytes = io.BytesIO(img)
# image_bytes.seek(0)
# image_blob = image_bytes.read()
# print('image_blob',image_blob)
# print('image_bytes',image_bytes)
# cursor.execute('INSERT INTO fingerprints (id, image) VALUES (?, ?)',
#                (user_id, image_blob))

# conn.commit()
# conn.close()

# print(f"Fingerprint saved with ID: {user_id}")



## list prints


# List prints
conn = sqlite3.connect('fingerprints3.db')
cursor = conn.cursor()

cursor.execute('SELECT id, image FROM fingerprints')
prints = cursor.fetchall()

import os

for print_id, print_image_blob in prints:
    print(f"Print ID: {print_id}")
    print(f"blob  {print_image_blob}")
    image_bytes = io.BytesIO(print_image_blob)
    image_bytes.seek(0)
    image_bytes = io.BytesIO(print_image_blob)
    image_bytes.seek(0)
    random_filename = str(uuid.uuid4()) + '.jpg'
    with open(random_filename, 'wb') as f:
        f.write(image_bytes.read())
    zkfp2.show_image(random_filename.encode())
    os.remove(random_filename)

conn.close()




