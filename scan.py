import sqlite3
import base64
from datetime import datetime
from pyzkfp import ZKFP2
from PIL import Image
import io


# Global ZKFP2 device instance
zkfp2 = None

def init_device():
    """Initialize the global ZKFP2 device."""
    global zkfp2
    try:
        zkfp2 = ZKFP2()
        zkfp2.Init()
        
        device_count = zkfp2.GetDeviceCount()
        print(f"{device_count} devices found")
        
        if device_count == 0:
            raise Exception("No fingerprint devices found")
        
        zkfp2.OpenDevice(0)
        print("Device connected successfully")
        return True
        
    except Exception as e:
        print(f"Error connecting to device: {e}")
        return False

def terminate_device():
    """Terminate the global ZKFP2 device."""
    global zkfp2
    if zkfp2:
        zkfp2.Terminate()
        zkfp2 = None
        print("Device disconnected")


class FingerprintScanner:
    def __init__(self, db_path="fingerprints.db"):
        """Initialize the fingerprint scanner with database connection."""
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for storing fingerprints."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                template BLOB NOT NULL,
                image BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def connect_device(self):
        """Connect to the fingerprint scanner device."""
        global zkfp2
        if zkfp2 is None:
            return init_device()
        return True
    
    def disconnect_device(self):
        """Disconnect from the fingerprint scanner device."""
        terminate_device()
    
    def capture_fingerprint(self):
        """Capture a single fingerprint."""
        global zkfp2
        if not zkfp2:
            raise Exception("Device not connected")
        
        print("Place finger on scanner...")
        while True:
            capture = zkfp2.AcquireFingerprint()
            if capture:
                tmp, img = capture
                print("Fingerprint captured successfully")
                return tmp, img
    
    def register_fingerprint(self, user_id, name):
        """
        Register a new fingerprint by capturing 3 samples and storing in database.
        
        Args:
            user_id (str): Unique identifier for the user
            name (str): Name of the person
            
        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            if not self.connect_device():
                return False
            
            print(f"Registering fingerprint for {name} (ID: {user_id})")
            print("Please place your finger on the scanner 3 times...")
            
            templates = []
            final_image = None
            
            # Capture 3 fingerprint samples
            for i in range(3):
                print(f"Capture {i+1}/3 - Place finger on scanner")
                tmp, img = self.capture_fingerprint()
                templates.append(tmp)
                if i == 0:  # Save the first image
                    final_image = img
                print(f"Sample {i+1} captured. Please lift your finger.")
                # if i < 2:
                #     input("Press Enter when ready for next capture...")
            
            # Merge templates
            global zkfp2
            reg_temp, reg_temp_len = zkfp2.DBMerge(*templates)
            # zkfp2.DBAdd(user_id, reg_temp)
            print('merged')
            # Convert image to bytes for storage
            image_bytes = None
            if final_image:
                image_bytes = base64.b64encode(final_image).decode('utf-8')
            print('image_bytes',image_bytes)
            # image_bytes = 'asbd'
            # # Store in database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO fingerprints (user_id, name, template, image)
                VALUES (?, ?, ?, ?)
            ''', (user_id, name, reg_temp, image_bytes))
            
            conn.commit()
            conn.close()
            
            print(f"Fingerprint registered successfully for {name}")
            
            # Display the captured image
            if final_image:
                zkfp2.show_image(final_image)
            
            self.disconnect_device()
            return True
            
        except Exception as e:
            print(f"Error during registration: {e}")
            self.disconnect_device()
            return False
    
    def match_fingerprint(self):
        """
        Match a captured fingerprint against all stored fingerprints in database.
        
        Returns:
            dict: Match result with user info if found, None if no match
        """
        try:
            if not self.connect_device():
                return None
            
            print("Place finger on scanner for matching...")
            tmp, img = self.capture_fingerprint()
            
            # Get all stored fingerprints from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, user_id, name, template FROM fingerprints')
            stored_prints = cursor.fetchall()
            conn.close()
            
            if not stored_prints:
                print("No fingerprints stored in database")
                self.disconnect_device()
                return None
            
            print(f"Matching against {len(stored_prints)} stored fingerprints...")
            
            # Try to match against each stored fingerprint
            for db_id, user_id, name, stored_template in stored_prints:
                try:
                    # Use DBMatch to compare fingerprints
                    global zkfp2
                    match_score = zkfp2.DBMatch(tmp, stored_template)
                    
                    # Threshold for match (adjust as needed)
                    if match_score > 60:  # Typical threshold is 60-80
                        result = {
                            'matched': True,
                            'user_id': user_id,
                            'name': name,
                            'match_score': match_score,
                            'db_id': db_id
                        }
                        print(f"Match found! User: {name} (ID: {user_id}) - Score: {match_score}")
                        
                        # Display the captured image
                        zkfp2.show_image(img)
                        
                        self.disconnect_device()
                        return result
                        
                except Exception as e:
                    print(f"Error matching against {name}: {e}")
                    continue
            
            print("No match found")
            self.disconnect_device()
            return {'matched': False, 'message': 'No matching fingerprint found'}
            
        except Exception as e:
            print(f"Error during matching: {e}")
            self.disconnect_device()
            return None
    
    def list_registered_users(self):
        """List all registered users in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, name, created_at FROM fingerprints ORDER BY created_at DESC')
        users = cursor.fetchall()
        conn.close()
        
        if users:
            print("\nRegistered Users:")
            print("-" * 50)
            for user_id, name, created_at in users:
                print(f"ID: {user_id} | Name: {name} | Registered: {created_at}")
        else:
            print("No users registered")
        
        return users
    
    def delete_user(self, user_id):
        """Delete a user's fingerprint from the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM fingerprints WHERE user_id = ?', (user_id,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            print(f"User {user_id} deleted successfully")
            return True
        else:
            print(f"User {user_id} not found")
            return False


def main():
    """Main function to demonstrate usage."""
    scanner = FingerprintScanner()
    
    while True:
        print("\n" + "="*50)
        print("Fingerprint Scanner System")
        print("="*50)
        print("1. Register new fingerprint")
        print("2. Match fingerprint")
        print("3. List registered users")
        print("4. Delete user")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == '1':
            user_id = input("Enter user ID: ").strip()
            name = input("Enter name: ").strip()
            if user_id and name:
                scanner.register_fingerprint(user_id, name)
            else:
                print("User ID and name are required")
        
        elif choice == '2':
            result = scanner.match_fingerprint()
            if result and result.get('matched'):
                print(f"\nAccess granted for {result['name']}")
            else:
                print("\nAccess denied - No match found")
        
        elif choice == '3':
            scanner.list_registered_users()
        
        elif choice == '4':
            user_id = input("Enter user ID to delete: ").strip()
            if user_id:
                scanner.delete_user(user_id)
            else:
                print("User ID is required")
        
        elif choice == '5':
            print("Goodbye!")
            break
        
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
