import sqlite3
import uuid
import sys
from pyzkfp import ZKFP2
import time



DATABASE_FILE = "test-1.db"

# --- SQLite Database Functions ---

def init_db():
    """Initializes the SQLite database and creates the table if it doesn't exist."""
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                fingerprint_template BLOB NOT NULL
            )
        """)
        conn.commit()

def save_fingerprint(user_id, template_data):
    """Saves a user's fingerprint template to the SQLite database."""
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (id, fingerprint_template) VALUES (?, ?)", (user_id, template_data))
        conn.commit()

def get_all_templates():
    """Retrieves all fingerprint templates and their IDs from the database."""
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, fingerprint_template FROM users")
        return cursor.fetchall()

# --- ZKTeco Fingerprint Functions ---

def init_device():
    """Initializes the ZKTeco fingerprint device."""
    zkfp2 = ZKFP2()
    # The Init() method returns 0 on success.
    if zkfp2.Init() != 0:
        print("Error initializing ZKFP2.")
        # return None
    
    device_count = zkfp2.GetDeviceCount()
    zkfp2.OpenDevice(0)
    # if device_count <= 0:
    #     print("No devices found.")
    #     zkfp2.Terminate()
    #     return None
        
    # The OpenDevice() method returns 0 on success.
    # if zkfp2.OpenDevice(0) != 0:
    #     print("Error opening device.")
    #     zkfp2.Terminate()
    #     return None
        
    return zkfp2

def scan_and_save_finger():
    """
    Scans a fingerprint, enrolls it, and saves it to the database with a random UUID.
    """
    zkfp2 = init_device()
    if not zkfp2:
        return
        
    print("Please place your finger on the scanner three times for enrollment.")
    templates = []
    for i in range(3):
        print(f"Waiting for scan {i+1}...")
        while True:
            capture = zkfp2.AcquireFingerprint()
            if capture:
                tmp, _ = capture
                templates.append(tmp)
                print(f"Scan {i+1} successful.")
                time.sleep(1) # Delay to prevent rapid re-scans
                break
    
    # Merge the templates into a final one
    # DBMerge returns a tuple: (return_code, merged_template, merged_template_size)
    ret_code, reg_temp, _ = zkfp2.DBMerge(templates[0], templates[1], templates[2])
    # The merge is successful if the return code is 0.
    if ret_code != 0:
        print(f"Error merging templates: {ret_code}")
        zkfp2.Terminate()
        return
    
    # Generate a random ID and save to DB
    user_id = str(uuid.uuid4())
    save_fingerprint(user_id, reg_temp)
    print(f"Fingerprint saved with ID: {user_id}")
    
    zkfp2.Terminate()

def match_finger():
    """
    Scans a new fingerprint and matches it against all templates in the database.
    """
    zkfp2 = init_device()
    if not zkfp2:
        return
        
    print("Please place your finger on the scanner for matching.")
    
    # Load all templates from the database
    db_templates = get_all_templates()
    if not db_templates:
        print("No fingerprints registered in the database.")
        zkfp2.Terminate()
        return
    
    # Wait for a new scan
    capture = None
    while not capture:
        capture = zkfp2.AcquireFingerprint()
        if not capture:
            time.sleep(0.5)
            
    tmp, _ = capture
    
    # Match against the database
    match_found = False
    for user_id, template_data in db_templates:
        # DBMatch returns a score; a score > 0 indicates a match.
        match_score = zkfp2.DBMatch(tmp, template_data)
        if match_score > 0:
            print(f"MATCH FOUND! User ID: {user_id}")
            match_found = True
            break
    
    if not match_found:
        print("NO MATCH FOUND.")
        
    zkfp2.Terminate()
    
# --- Main Script ---
if __name__ == "__main__":
    init_db()
    
    while True:
        print("\nOptions:")
        print("1. Scan and save a new fingerprint")
        print("2. Match a fingerprint")
        print("3. Exit")
        choice = input("Enter your choice: ")
        
        if choice == '1':
            scan_and_save_finger()
        elif choice == '2':
            match_finger()
        elif choice == '3':
            sys.exit()
        else:
            print("Invalid choice. Please try again.")

