from pyzkfp import ZKFP2
import sqlite3
import random

# Initialize database
def init_db():
    conn = sqlite3.connect('fingerprints-1.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS fingerprints (
        id INTEGER PRIMARY KEY,
        finger_id INTEGER UNIQUE,
        template BLOB
    )
    ''')
    conn.commit()
    conn.close()

# Store fingerprint
def store_finger():
    init_db()
    
    zkfp2 = ZKFP2()
    zkfp2.Init()
    zkfp2.OpenDevice(0)
    
    # Capture 3 samples
    templates = []
    for i in range(3):
        print(f"Place finger {i+1}/3")
        while True:
            capture = zkfp2.AcquireFingerprint()
            if capture:
                templates.append(capture[0])
                break
    
    # Merge and store
    if templates:
        reg_temp, _ = zkfp2.DBMerge(*templates)
        finger_id = random.randint(1, 9999)
        
        conn = sqlite3.connect('fingerprints-1.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO fingerprints (finger_id, template) VALUES (?, ?)', 
                      (finger_id, bytes(reg_temp)))
        conn.commit()
        conn.close()
        
        print(f"Stored with ID: {finger_id}")
    
    zkfp2.Terminate()

# List all fingerprints
def list_fingers():
    init_db()
    
    conn = sqlite3.connect('fingerprints-1.db')
    cursor = conn.cursor()
    cursor.execute('SELECT finger_id,template FROM fingerprints ORDER BY finger_id')
    fingers = cursor.fetchall()
    print(fingers)
    if fingers:
        print("Stored Fingerprint IDs:")
        for finger_id,template in fingers:
            print(f"ID: {finger_id}")
            print(f"ID: {template}")
    else:
        print("No fingerprints stored")
    
    conn.close()

def match_fingerprint(finger_id):
    """
    Match a captured fingerprint with a stored template by ID
    
    Args:
        finger_id (int): The ID of the fingerprint to match against
    
    Returns:
        bool: True if match successful, False otherwise
    """
    # First check if the fingerprint ID exists
    conn = sqlite3.connect('fingerprints-1.db')
    cursor = conn.cursor()
    cursor.execute('SELECT template FROM fingerprints WHERE finger_id = ?', (finger_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"❌ No fingerprint found with ID: {finger_id}")
        return False
    
    # Get the stored template
    stored_template = result[0]
    
    # Initialize fingerprint scanner
    zkfp2 = ZKFP2()
    try:
        zkfp2.Init()
        device_count = zkfp2.GetDeviceCount()
        if device_count == 0:
            print("❌ No fingerprint devices found")
            return False
        
        zkfp2.OpenDevice(0)
        
        # Capture current fingerprint
        print("👆 Please place your finger on the scanner...")
        current_temp = None
        while not current_temp:
            capture = zkfp2.AcquireFingerprint()
            if capture:
                current_temp, img = capture
        
        # Perform matching
        match_score = zkfp2.DBMatch(current_temp, stored_template)
        print(f"📊 Match score: {match_score}")
        
        # Threshold for match (adjust based on your device)
        if match_score and match_score > 50:
            print(f"✅ Fingerprint matched successfully with ID: {finger_id}")
            return True
        else:
            print(f"❌ Fingerprint does not match ID: {finger_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error during matching: {e}")
        return False
    finally:
        try:
            zkfp2.Terminate()
        except:
            pass
# Example usage:
if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Store a new fingerprint
    # store_finger()
    
    # List all stored fingerprints
    # list_fingers()
    match_fingerprint(460)