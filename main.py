import tkinter as tk
from tkinter import ttk, messagebox, font
import requests
import json
import base64
import io
from datetime import datetime
import threading
import sys
import os

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Add parent directory to path to import fingerprint modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from py3 import store_finger, match_fingerprint, list_fingers, init_db


class FingerprintApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Fingerprint Registration System")
        self.root.geometry("900x700")
        self.root.configure(bg='#f0f0f0')
        
        # Initialize database
        init_db()
        
        # Configure styles
        self.setup_styles()
        
        # Create main notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Load settings
        self.settings = self.load_settings()
        
        # Create tabs
        self.create_register_tab()
        self.create_match_tab()
        self.create_settings_tab()
        
        # API URLs from settings
        server_url = self.settings.get('server_url', 'http://localhost:4111')
        self.api_base_url = server_url + "/api/v1/service-request/passport/"
        self.fingerprint_api_url = server_url + "/api/v1/fingerprint/register"
        self.fingerprint_lookup_url = server_url + "/api/v1/finger/passport"
        
    def setup_styles(self):
        """Configure custom styles for the application"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure custom styles
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'), background='#f0f0f0')
        style.configure('Heading.TLabel', font=('Arial', 12, 'bold'), background='#f0f0f0')
        style.configure('Info.TLabel', font=('Arial', 10), background='#f0f0f0')
        style.configure('Success.TLabel', font=('Arial', 10), foreground='#28a745', background='#f0f0f0')
        style.configure('Error.TLabel', font=('Arial', 10), foreground='#dc3545', background='#f0f0f0')
        
    def create_register_tab(self):
        """Create the registration tab"""
        register_frame = ttk.Frame(self.notebook)
        self.notebook.add(register_frame, text="Register")
        
        # Main container with padding
        main_container = ttk.Frame(register_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_container, text="Fingerprint Registration", style='Title.TLabel')
        title_label.pack(pady=(0, 10))
        
        # Compact top bar: Search + Register side by side
        top_frame = ttk.LabelFrame(main_container, text="Search & Register", padding=10)
        top_frame.pack(fill='x', pady=(0, 10))
        row1 = ttk.Frame(top_frame)
        row1.pack(fill='x')
        ttk.Label(row1, text="Passport Number:", style='Heading.TLabel').pack(side='left', padx=(0, 5))
        self.passport_entry = ttk.Entry(row1, font=('Arial', 12), width=18)
        self.passport_entry.pack(side='left', padx=(0, 8))
        self.search_btn = ttk.Button(row1, text="Search", command=self.search_passport)
        self.search_btn.pack(side='left', padx=(0, 15))
        self.register_fp_btn = ttk.Button(row1, text="Register Fingerprint",
                                         command=self.register_fingerprint, state='disabled')
        self.register_fp_btn.pack(side='left', padx=(0, 8))
        self.cancel_register_btn = ttk.Button(row1, text="Cancel", command=self._cancel_registration)
        self.cancel_register_btn.pack(side='left')
        self.cancel_register_btn.pack_forget()
        self.loading_label = ttk.Label(top_frame, text="", style='Info.TLabel')
        self.loading_label.pack(anchor='w', pady=(6, 0))
        self.register_status_label = ttk.Label(top_frame, text="", style='Info.TLabel')
        self.register_status_label.pack(anchor='w', pady=(2, 0))
        self.registration_cancelled = False
        self.current_user_data = None
        
        # User details section (gets most of the space)
        self.details_frame = ttk.LabelFrame(main_container, text="User Details", padding=15)
        self.details_frame.pack(fill='both', expand=True, pady=(0, 0))
        self.details_frame.pack_forget()
        
    def create_match_tab(self):
        """Create the matching tab"""
        match_frame = ttk.Frame(self.notebook)
        self.notebook.add(match_frame, text="Match")
        
        # Main container with padding
        main_container = ttk.Frame(match_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_container, text="Fingerprint Matching", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Passport search section
        search_frame = ttk.LabelFrame(main_container, text="Passport Search", padding=15)
        search_frame.pack(fill='x', pady=(0, 20))
        
        # Passport number input
        passport_label = ttk.Label(search_frame, text="Passport Number:", style='Heading.TLabel')
        passport_label.pack(anchor='w', pady=(0, 5))
        
        passport_input_frame = ttk.Frame(search_frame)
        passport_input_frame.pack(fill='x', pady=(0, 10))
        
        self.match_passport_entry = ttk.Entry(passport_input_frame, font=('Arial', 12), width=20)
        self.match_passport_entry.pack(side='left', padx=(0, 10))
        
        self.match_search_btn = ttk.Button(passport_input_frame, text="Search", command=self.match_search_passport)
        self.match_search_btn.pack(side='left')
        
        # Loading indicator
        self.match_loading_label = ttk.Label(search_frame, text="", style='Info.TLabel')
        self.match_loading_label.pack(anchor='w', pady=(5, 0))
        
        # User details section
        self.match_details_frame = ttk.LabelFrame(main_container, text="User Details", padding=15)
        self.match_details_frame.pack(fill='both', expand=True, pady=(0, 20))
        
        # Initially hide details frame
        self.match_details_frame.pack_forget()
        
        # Fingerprint matching section
        match_section = ttk.LabelFrame(main_container, text="Fingerprint Matching", padding=15)
        match_section.pack(fill='x')
        
        # Finger ID input
        id_frame = ttk.Frame(match_section)
        id_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(id_frame, text="Finger ID:", style='Heading.TLabel').pack(side='left', padx=(0, 10))
        self.finger_id_entry = ttk.Entry(id_frame, font=('Arial', 12), width=15)
        self.finger_id_entry.pack(side='left')
        
        # Match button
        self.match_btn = ttk.Button(match_section, text="Match Fingerprint", command=self.match_fingerprint)
        self.match_btn.pack(pady=10)
        
        # Match result
        self.match_result_label = ttk.Label(match_section, text="", style='Info.TLabel')
        self.match_result_label.pack(pady=(5, 0))
        
        # Store match user data
        self.current_match_user_data = None
        
    def create_settings_tab(self):
        """Create the settings tab"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")
        
        # Main container with padding
        main_container = ttk.Frame(settings_frame)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_container, text="Application Settings", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Server Configuration Section
        server_frame = ttk.LabelFrame(main_container, text="Server Configuration", padding=15)
        server_frame.pack(fill='x', pady=(0, 20))
        
        # Server URL input
        url_label = ttk.Label(server_frame, text="Server URL:", style='Heading.TLabel')
        url_label.pack(anchor='w', pady=(0, 5))
        
        url_help_label = ttk.Label(server_frame, text="Enter the base server URL (e.g., http://192.168.1.100:4111)", 
                                  style='Info.TLabel')
        url_help_label.pack(anchor='w', pady=(0, 10))
        
        self.server_url_entry = ttk.Entry(server_frame, font=('Arial', 12), width=50)
        self.server_url_entry.pack(fill='x', pady=(0, 10))
        
        # Load current setting
        current_url = self.settings.get('server_url', 'http://localhost:4111')
        self.server_url_entry.insert(0, current_url)
        
        # Buttons frame
        buttons_frame = ttk.Frame(server_frame)
        buttons_frame.pack(fill='x', pady=(10, 0))
        
        # Test connection button
        self.test_btn = ttk.Button(buttons_frame, text="Test Connection", command=self.test_connection)
        self.test_btn.pack(side='left', padx=(0, 10))
        
        # Save settings button
        self.save_btn = ttk.Button(buttons_frame, text="Save Settings", command=self.save_settings_ui)
        self.save_btn.pack(side='left')
        
        # Reset to default button
        reset_btn = ttk.Button(buttons_frame, text="Reset to Default", command=self.reset_to_default)
        reset_btn.pack(side='right')
        
        # Status label
        self.settings_status_label = ttk.Label(server_frame, text="", style='Info.TLabel')
        self.settings_status_label.pack(anchor='w', pady=(10, 0))
        
        # Application Info Section
        info_frame = ttk.LabelFrame(main_container, text="Application Information", padding=15)
        info_frame.pack(fill='x', pady=(0, 20))
        
        info_text = """
Fingerprint Registration System v1.0

This application allows you to:
• Search passport information via API
• Register fingerprints linked to passport data
• Match fingerprints against stored templates
• Configure server settings

Settings are automatically saved to your local machine.
        """
        
        info_label = ttk.Label(info_frame, text=info_text.strip(), style='Info.TLabel', justify='left')
        info_label.pack(anchor='w')
        
        # Database Info Section
        db_frame = ttk.LabelFrame(main_container, text="Database Information", padding=15)
        db_frame.pack(fill='x')
        
        # Database status
        db_status_frame = ttk.Frame(db_frame)
        db_status_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(db_status_frame, text="Database File:", style='Heading.TLabel').pack(side='left')
        ttk.Label(db_status_frame, text="fingerprints-1.db", style='Info.TLabel').pack(side='left', padx=(10, 0))
        
        # Refresh database info button
        refresh_db_btn = ttk.Button(db_frame, text="Refresh Database Info", command=self.refresh_db_info)
        refresh_db_btn.pack(anchor='w', pady=(0, 10))
        
        # Database info display
        self.db_info_label = ttk.Label(db_frame, text="", style='Info.TLabel')
        self.db_info_label.pack(anchor='w')
        
        # Load initial database info
        self.refresh_db_info()
        
    def search_passport(self):
        """Search for passport information via API"""
        passport_number = self.passport_entry.get().strip()
        if not passport_number:
            messagebox.showerror("Error", "Please enter a passport number")
            return
            
        # Disable search button and show loading
        self.search_btn.configure(state='disabled')
        self.loading_label.configure(text="Searching...", style='Info.TLabel')
        
        # Run API call in separate thread to prevent UI freezing
        thread = threading.Thread(target=self._api_search_thread, args=(passport_number,))
        thread.daemon = True
        thread.start()
        
    def _api_search_thread(self, passport_number):
        """API search in separate thread"""
        try:
            url = f"{self.api_base_url}{passport_number}"
            response = requests.get(url, timeout=10)
            
            # Schedule UI update in main thread
            self.root.after(0, self._handle_api_response, response, passport_number)
            
        except requests.exceptions.RequestException as e:
            self.root.after(0, self._handle_api_error, str(e))
            
    def _handle_api_response(self, response, passport_number):
        """Handle API response in main thread"""
        try:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.current_user_data = data.get('data')
                    self._display_user_details(self.current_user_data)
                    self.loading_label.configure(text="User found successfully!", style='Success.TLabel')
                    
                    # Check fingerprint status and update button accordingly
                    fingerprint_info = self.current_user_data.get('fingerprint', {})
                    is_registered = fingerprint_info.get('registered', False)
                    
                    if is_registered:
                        self.register_fp_btn.configure(text="Re-register Fingerprint", state='normal')
                        self.register_status_label.configure(text="⚠️ User already has fingerprint registered", style='Info.TLabel')
                    else:
                        self.register_fp_btn.configure(text="Register Fingerprint", state='normal')
                        self.register_status_label.configure(text="Ready to register fingerprint", style='Info.TLabel')
                else:
                    self._handle_api_error(data.get('message', 'Unknown error'))
            else:
                self._handle_api_error(f"HTTP {response.status_code}: {response.text}")
                
        except json.JSONDecodeError:
            self._handle_api_error("Invalid response format")
        except Exception as e:
            self._handle_api_error(str(e))
        finally:
            self.search_btn.configure(state='normal')
            
    def _handle_api_error(self, error_message):
        """Handle API errors"""
        self.loading_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        self.search_btn.configure(state='normal')
        self.details_frame.pack_forget()
        self.register_fp_btn.configure(state='disabled')
        self.current_user_data = None
        
    def _display_user_details(self, user_data):
        """Display user details with left (details) and right (photo/emoji) layout"""
        for widget in self.details_frame.winfo_children():
            widget.destroy()
        self.details_frame.pack(fill='x', pady=(0, 20))
        details_container, _ = self._build_details_with_photo(self.details_frame, user_data, is_match_tab=False)
        self._fill_detail_sections(details_container, user_data)

    def _fill_detail_sections(self, details_container, user_data):
        """Fill personal, fingerprint, service, and location sections into details_container."""
        personal_frame = ttk.LabelFrame(details_container, text="Personal Information", padding=10)
        personal_frame.pack(fill='x', pady=(0, 10))
        self._add_detail_row(personal_frame, "Full Name:", user_data.get('full_name', 'N/A'))
        self._add_detail_row(personal_frame, "Passport Number:", user_data.get('passport_number', 'N/A'))
        self._add_detail_row(personal_frame, "Phone:", user_data.get('phone', 'N/A'))
        self._add_detail_row(personal_frame, "Father's Name:", user_data.get('father_name', 'N/A'))
        self._add_detail_row(personal_frame, "Birth Date:", self._format_date(user_data.get('birth_date')))
        self._add_detail_row(personal_frame, "Gender:", user_data.get('gender', 'N/A'))
        self._add_detail_row(personal_frame, "Nationality:", user_data.get('nationality', 'N/A'))
        self._add_detail_row(personal_frame, "Profession:", user_data.get('profession', 'N/A'))
        self._add_detail_row(personal_frame, "Religion:", user_data.get('religion', 'N/A'))
        self._add_detail_row(personal_frame, "Address:", user_data.get('address', 'N/A'))
        fingerprint_info = user_data.get('fingerprint', {})
        fp_status_frame = ttk.LabelFrame(details_container, text="Fingerprint Status", padding=10)
        fp_status_frame.pack(fill='x', pady=(0, 10))
        is_registered = fingerprint_info.get('registered', False)
        has_template = fingerprint_info.get('has_template', False)
        status_text = "✅ Registered" if is_registered else "❌ Not Registered"
        template_text = "✅ Template Available" if has_template else "❌ No Template"
        self._add_detail_row(fp_status_frame, "Registration Status:", status_text)
        self._add_detail_row(fp_status_frame, "Template Status:", template_text)
        service_frame = ttk.LabelFrame(details_container, text="Service Information", padding=10)
        service_frame.pack(fill='x', pady=(0, 10))
        self._add_detail_row(service_frame, "Amount:", f"৳{user_data.get('amount', 0)}")
        self._add_detail_row(service_frame, "Delivery Date:", self._format_date(user_data.get('delivery_date')))
        if user_data.get('branch') or user_data.get('country'):
            location_frame = ttk.LabelFrame(details_container, text="Location Information", padding=10)
            location_frame.pack(fill='x', pady=(0, 10))
            if user_data.get('branch'):
                branch = user_data['branch']
                self._add_detail_row(location_frame, "Branch Name:", branch.get('name', 'N/A'))
                self._add_detail_row(location_frame, "Branch Address:", branch.get('address', 'N/A'))
            if user_data.get('country'):
                country = user_data['country']
                self._add_detail_row(location_frame, "Country:", country.get('name', 'N/A'))
        
    def _add_detail_row(self, parent, label, value):
        """Add a detail row with label and value"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill='x', pady=2)
        
        label_widget = ttk.Label(row_frame, text=label, style='Heading.TLabel', width=20, anchor='w')
        label_widget.pack(side='left')
        
        value_widget = ttk.Label(row_frame, text=str(value) if value else 'N/A', style='Info.TLabel', anchor='w')
        value_widget.pack(side='left', fill='x', expand=True)
        
    def _format_date(self, date_str):
        """Format date string for display"""
        if not date_str:
            return 'N/A'
        try:
            # Parse the date and format it nicely
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date_obj.strftime('%B %d, %Y')
        except:
            return date_str

    def _get_user_photo_or_emoji(self, user_data):
        """
        Get user photo from data.user (or data) as URL or base64.
        Returns (photo_image_for_tk, emoji_fallback).
        If photo is available: (PhotoImage, None). If not: (None, '👨' or '👩').
        """
        gender = (user_data.get('gender') or '').lower()
        emoji = '👩' if gender == 'female' else '👨'
        photo_source = None
        user_obj = user_data.get('user') or {}
        for key in ('photo', 'image', 'image_url', 'avatar'):
            if user_obj.get(key):
                photo_source = user_obj.get(key)
                break
        if not photo_source:
            photo_source = user_data.get('photo') or user_data.get('image') or user_data.get('image_url')
        if not photo_source or not HAS_PIL:
            return None, emoji
        try:
            if isinstance(photo_source, str) and photo_source.startswith(('http://', 'https://')):
                r = requests.get(photo_source, timeout=5)
                r.raise_for_status()
                img = Image.open(io.BytesIO(r.content))
            else:
                # Assume base64
                raw = base64.b64decode(photo_source)
                img = Image.open(io.BytesIO(raw))
            img = img.convert('RGB')
            img.thumbnail((280, 360), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img), None
        except Exception:
            return None, emoji

    def _build_details_with_photo(self, parent_frame, user_data, is_match_tab=False):
        """
        Build two-column layout: left = scrollable details, right = photo or emoji.
        Returns (details_container for adding rows, right_frame, photo_ref to keep).
        """
        # Outer horizontal split: left = details, right = photo (expands to fill empty space)
        content = ttk.Frame(parent_frame)
        content.pack(fill='both', expand=True, padx=5, pady=5)
        left_panel = ttk.Frame(content)
        left_panel.pack(side='left', fill='y', expand=False)
        right_panel = ttk.Frame(content)
        right_panel.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=10)
        # Right side: photo/emoji fills available space
        photo_frame = ttk.LabelFrame(right_panel, text="Photo", padding=8)
        photo_frame.pack(fill='both', expand=True)
        photo_inner = ttk.Frame(photo_frame)
        photo_inner.pack(fill='both', expand=True)
        photo_ref = [None]  # keep ref so PhotoImage is not garbage-collected
        photo_image, emoji = self._get_user_photo_or_emoji(user_data)
        if photo_image:
            photo_ref[0] = photo_image
            lbl = ttk.Label(photo_inner, image=photo_image)
            lbl.pack(expand=True)
        else:
            lbl = tk.Label(photo_inner, text=emoji, font=('Segoe UI Emoji', 120), bg='#f8f9fa', fg='#495057')
            lbl.pack(expand=True, padx=20, pady=20)
        # Left: scrollable details (no horizontal expand so no grey gap)
        scroll_frame = ttk.Frame(left_panel)
        scroll_frame.pack(fill='y', expand=False)
        canvas = tk.Canvas(scroll_frame, height=360, bg='#f8f9fa')
        scrollbar = ttk.Scrollbar(scroll_frame, orient='vertical', command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        scrollbar.pack(side='left', fill='y')
        canvas.pack(side='left', fill='y', expand=False)
        return scrollable_frame, photo_ref

    def register_fingerprint(self):
        """Register fingerprint for the current user"""
        if not self.current_user_data:
            messagebox.showerror("Error", "No user data available")
            return
        
        # Check if user already has fingerprint registered
        fingerprint_info = self.current_user_data.get('fingerprint', {})
        is_registered = fingerprint_info.get('registered', False)
        
        if is_registered:
            # Ask for confirmation to re-register
            result = messagebox.askyesno(
                "Fingerprint Already Registered", 
                "This user already has a fingerprint registered. Do you want to re-register it?\n\n"
                "This will replace the existing fingerprint data."
            )
            if not result:
                return
            
        self.registration_cancelled = False
        self.register_fp_btn.configure(state='disabled')
        self.cancel_register_btn.pack(side='left')
        status_text = "Re-registering fingerprint..." if is_registered else "Registering fingerprint..."
        self.register_status_label.configure(text=f"{status_text} Please follow scanner instructions.",
                                           style='Info.TLabel')
        thread = threading.Thread(target=self._register_fingerprint_thread)
        thread.daemon = True
        thread.start()

    def _cancel_registration(self):
        """Set flag so registration thread can exit; UI is updated by the thread or on next check."""
        self.registration_cancelled = True
        self.register_status_label.configure(text="Cancelling...", style='Info.TLabel')
        
    def _register_fingerprint_thread(self):
        """Register fingerprint in separate thread"""
        try:
            # Capture fingerprint using local scanner
            from pyzkfp import ZKFP2
            import base64
            
            # Update GUI: Initializing device
            self.root.after(0, self._update_registration_status, "🔧 Initializing fingerprint device...")
            
            zkfp2 = ZKFP2()
            zkfp2.Init()
            
            # Update GUI: Setting exposure parameters
            self.root.after(0, self._update_registration_status, "⚙️ Setting exposure parameters...")
            
            zkfp2.OpenDevice(0)
            
            # Update GUI: Device ready
            self.root.after(0, self._update_registration_status, "✅ Device connected successfully")
            if self.registration_cancelled:
                zkfp2.Terminate()
                self.root.after(0, self._fingerprint_registration_cancelled)
                return
            templates = []
            for i in range(3):
                if self.registration_cancelled:
                    zkfp2.Terminate()
                    self.root.after(0, self._fingerprint_registration_cancelled)
                    return
                self.root.after(0, self._update_registration_status, f"👆 Place finger {i+1}/3 - Waiting for finger on scanner... (Cancel to abort)")
                while True:
                    if self.registration_cancelled:
                        zkfp2.Terminate()
                        self.root.after(0, self._fingerprint_registration_cancelled)
                        return
                    capture = zkfp2.AcquireFingerprint()
                    if capture:
                        templates.append(capture[0])
                        self.root.after(0, self._update_registration_status, f"✅ Finger {i+1}/3 captured successfully! Please lift your finger.")
                        break
            if self.registration_cancelled:
                zkfp2.Terminate()
                self.root.after(0, self._fingerprint_registration_cancelled)
                return
            # Update GUI: Processing template
            self.root.after(0, self._update_registration_status, "🔄 Processing fingerprint template...")
            
            # Use first template (avoiding DBMerge issues)
            # reg_temp = templates[0]
            reg_temp, _ = zkfp2.DBMerge(*templates)
            
            # Convert template to base64 for API
            template_b64 = base64.b64encode(bytes(reg_temp)).decode('utf-8')
            
            zkfp2.Terminate()
            
            # Update GUI: Sending to server
            self.root.after(0, self._update_registration_status, "📡 Sending fingerprint data to server...")
            
            # Send to API
            passport_number = self.current_user_data.get('passport_number')
            api_data = {
                "passport_number": passport_number,
                "template": template_b64
            }
            
            response = requests.post(
                self.fingerprint_api_url,
                json=api_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            # Print response for debugging
            print(f"API Response Status: {response.status_code}")
            print(f"API Response Text: {response.text}")
            
            if response.status_code in [200, 201]:  # Accept both 200 and 201
                try:
                    result = response.json()
                    print(f"API Response JSON: {result}")
                    
                    if result.get('success', False):
                        self.root.after(0, self._fingerprint_registration_success)
                    else:
                        self.root.after(0, self._fingerprint_registration_error, result.get('message', 'API registration failed'))
                except json.JSONDecodeError:
                    self.root.after(0, self._fingerprint_registration_error, "Invalid JSON response from API")
            else:
                self.root.after(0, self._fingerprint_registration_error, f"API Error: {response.status_code} - {response.text}")
                
        except Exception as e:
            self.root.after(0, self._fingerprint_registration_error, str(e))
    
    def _update_registration_status(self, message):
        """Update registration status in GUI"""
        self.register_status_label.configure(text=message, style='Info.TLabel')
            
    def _fingerprint_registration_cancelled(self):
        """Handle user cancellation of fingerprint registration"""
        self.cancel_register_btn.pack_forget()
        self.register_fp_btn.configure(state='normal')
        self.register_status_label.configure(text="Registration cancelled.", style='Info.TLabel')
        messagebox.showinfo("Cancelled", "Fingerprint registration was cancelled.")

    def _fingerprint_registration_success(self):
        """Handle successful fingerprint registration"""
        self.cancel_register_btn.pack_forget()
        self.register_status_label.configure(text="Fingerprint registered successfully!", style='Success.TLabel')
        self.register_fp_btn.configure(state='normal')
        messagebox.showinfo("Success", "Fingerprint has been registered successfully!")

    def _fingerprint_registration_error(self, error_message):
        """Handle fingerprint registration error"""
        self.cancel_register_btn.pack_forget()
        self.register_status_label.configure(text=f"Registration failed: {error_message}", style='Error.TLabel')
        self.register_fp_btn.configure(state='normal')
        messagebox.showerror("Error", f"Fingerprint registration failed: {error_message}")
        
    def match_fingerprint(self):
        """Match fingerprint with stored template"""
        if not self.current_match_user_data:
            messagebox.showerror("Error", "Please search for a passport first")
            return
            
        self.match_btn.configure(state='disabled')
        self.match_result_label.configure(text="Matching fingerprint... Please place finger on scanner.", 
                                        style='Info.TLabel')
        
        # Run matching in separate thread
        thread = threading.Thread(target=self._match_fingerprint_thread)
        thread.daemon = True
        thread.start()
        
    def _match_fingerprint_thread(self):
        """Match fingerprint in separate thread"""
        try:
            if not self.current_match_user_data:
                self.root.after(0, self._handle_match_error, "No user data available")
                return
            
            # Get stored template from API
            passport_number = self.current_match_user_data.get('passport_number')
            if not passport_number:
                self.root.after(0, self._handle_match_error, "No passport number available")
                return
            
            # Update GUI: Getting stored template
            self.root.after(0, self._update_match_status, "📡 Retrieving stored fingerprint template...")
            
            # Get stored template from fingerprint lookup API
            lookup_response = requests.get(f"{self.fingerprint_lookup_url}/{passport_number}", timeout=10)
            print(f"[MATCH TAB] Fingerprint lookup URL: {lookup_response.url}")

            print(f"[MATCH TAB] Fingerprint lookup response: {lookup_response.status_code}")
            print(f"[MATCH TAB] Fingerprint lookup response headers: {dict(lookup_response.headers)}")
            print(f"[MATCH TAB] Fingerprint lookup response text: {lookup_response.text}")
            
            if lookup_response.status_code != 200:
                self.root.after(0, self._handle_match_error, f"Failed to retrieve stored template: {lookup_response.status_code}")
                return
            
            lookup_data = lookup_response.json()
            if not lookup_data.get('success'):
                self.root.after(0, self._handle_match_error, lookup_data.get('message', 'Failed to retrieve template'))
                return
            
            stored_template_b64 = lookup_data.get('data', {}).get('template')
            if not stored_template_b64:
                self.root.after(0, self._handle_match_error, "No template found in API response")
                return
            
            # Decode stored template
            stored_template = base64.b64decode(stored_template_b64)
            
            # Capture live fingerprint using local scanner
            from pyzkfp import ZKFP2
            
            # Initialize device only if not already initialized
            if not hasattr(self, 'zkfp2') or self.zkfp2 is None:
                # Update GUI: Initializing device
                self.root.after(0, self._update_match_status, "🔧 Initializing fingerprint device...")
                
                self.zkfp2 = ZKFP2()
                self.zkfp2.Init()
                self.zkfp2.OpenDevice(0)
                
                # Update GUI: Device ready
                self.root.after(0, self._update_match_status, "✅ Device connected successfully")
            else:
                # Update GUI: Device already ready
                self.root.after(0, self._update_match_status, "✅ Using existing device connection")
            
            # Capture 3 samples for better accuracy
            templates = []
            for i in range(3):
                # Update GUI: Waiting for finger placement
                self.root.after(0, self._update_match_status, f"👆 Place finger {i+1}/3 - Waiting for finger on scanner...")
                
                while True:
                    capture = self.zkfp2.AcquireFingerprint()
                    if capture:
                        templates.append(capture[0])
                        # Update GUI: Finger captured
                        self.root.after(0, self._update_match_status, f"✅ Finger {i+1}/3 captured successfully! Please lift your finger.")
                        break
            
            # Update GUI: Processing template
            self.root.after(0, self._update_match_status, "🔄 Processing captured fingerprint...")
            
            # Merge captured templates
            live_template, _ = self.zkfp2.DBMerge(*templates)
            
            # Update GUI: Matching
            self.root.after(0, self._update_match_status, "🔍 Comparing fingerprints...")
            
            # Perform matching using ZKFP2
            match_result = self.zkfp2.DBMatch(stored_template, live_template)
            
            # Handle result
            self.root.after(0, self._handle_match_result, match_result > 0)
            
        except Exception as e:
            self.root.after(0, self._handle_match_error, str(e))
            
    def _update_match_status(self, message):
        """Update match status in GUI"""
        self.match_result_label.configure(text=message, style='Info.TLabel')
            
    def _handle_match_result(self, result):
        """Handle fingerprint match result"""
        self.match_btn.configure(state='normal')
        if result:
            self.match_result_label.configure(text="✅ Match successful", 
                                            style='Success.TLabel')
            messagebox.showinfo("Match Success", "Fingerprint matched successfully")
        else:
            self.match_result_label.configure(text="❌ No match found", 
                                            style='Error.TLabel')
            messagebox.showwarning("No Match", "Fingerprint does not match")
            
    def _handle_match_error(self, error_message):
        """Handle fingerprint match error"""
        self.match_btn.configure(state='normal')
        self.match_result_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        messagebox.showerror("Error", f"Matching failed: {error_message}")
    
    def load_settings(self):
        """Load settings from JSON file"""
        settings_file = "app_settings.json"
        default_settings = {
            "server_url": "http://localhost:4111",
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    return settings
            else:
                # Create default settings file
                with open(settings_file, 'w') as f:
                    json.dump(default_settings, f, indent=2)
                return default_settings
        except Exception as e:
            print(f"Error loading settings: {e}")
            return default_settings
    
    def save_settings_to_file(self, settings):
        """Save settings to JSON file"""
        settings_file = "app_settings.json"
        try:
            settings["last_updated"] = datetime.now().isoformat()
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    def save_settings_ui(self):
        """Save settings from UI"""
        new_url = self.server_url_entry.get().strip()
        
        # Validate URL
        if not new_url:
            messagebox.showerror("Error", "Server URL cannot be empty")
            return
        
        if not (new_url.startswith('http://') or new_url.startswith('https://')):
            messagebox.showerror("Error", "Server URL must start with http:// or https://")
            return
        
        # Update settings
        self.settings["server_url"] = new_url
        
        # Save to file
        if self.save_settings_to_file(self.settings):
            # Update API URLs
            self.api_base_url = new_url + "/api/v1/service-request/passport/"
            self.fingerprint_api_url = new_url + "/api/v1/fingerprint/register"
            self.fingerprint_lookup_url = new_url + "/api/v1/finger/passport"
            
            self.settings_status_label.configure(text="✅ Settings saved successfully!", style='Success.TLabel')
            messagebox.showinfo("Success", "Settings have been saved successfully!")
        else:
            self.settings_status_label.configure(text="❌ Failed to save settings", style='Error.TLabel')
            messagebox.showerror("Error", "Failed to save settings to file")
    
    def test_connection(self):
        """Test connection to the server"""
        test_url = self.server_url_entry.get().strip()
        
        if not test_url:
            messagebox.showerror("Error", "Please enter a server URL")
            return
        
        self.test_btn.configure(state='disabled')
        self.settings_status_label.configure(text="Testing connection...", style='Info.TLabel')
        
        # Run test in separate thread
        thread = threading.Thread(target=self._test_connection_thread, args=(test_url,))
        thread.daemon = True
        thread.start()
    
    def _test_connection_thread(self, test_url):
        """Test connection in separate thread"""
        try:
            # Test with a simple GET request to the base URL
            response = requests.get(test_url, timeout=5)
            self.root.after(0, self._handle_test_result, True, f"Connection successful! Status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.root.after(0, self._handle_test_result, False, str(e))
    
    def _handle_test_result(self, success, message):
        """Handle test connection result"""
        self.test_btn.configure(state='normal')
        if success:
            self.settings_status_label.configure(text=f"✅ {message}", style='Success.TLabel')
        else:
            self.settings_status_label.configure(text=f"❌ Connection failed: {message}", style='Error.TLabel')
    
    def reset_to_default(self):
        """Reset server URL to default"""
        default_url = "http://localhost:4111"
        self.server_url_entry.delete(0, tk.END)
        self.server_url_entry.insert(0, default_url)
        self.settings_status_label.configure(text="Reset to default URL", style='Info.TLabel')
    
    def refresh_db_info(self):
        """Refresh database information"""
        try:
            fingerprints = list_fingers()
            count = len(fingerprints) if fingerprints else 0
            
            db_info = f"Total fingerprints stored: {count}\n"
            if count > 0:
                db_info += f"Fingerprint IDs: {', '.join([str(fp[0]) for fp in fingerprints[:5]])}"
                if count > 5:
                    db_info += f" and {count - 5} more..."
            
            self.db_info_label.configure(text=db_info)
        except Exception as e:
            self.db_info_label.configure(text=f"Error reading database: {e}")
            
    def match_search_passport(self):
        """Search for passport information via API"""
        passport_number = self.match_passport_entry.get().strip()
        if not passport_number:
            messagebox.showerror("Error", "Please enter a passport number")
            return
            
        # Disable search button and show loading
        self.match_search_btn.configure(state='disabled')
        self.match_loading_label.configure(text="Searching...", style='Info.TLabel')
        
        # Run API call in separate thread to prevent UI freezing
        thread = threading.Thread(target=self._match_api_search_thread, args=(passport_number,))
        thread.daemon = True
        thread.start()
        
    def _match_api_search_thread(self, passport_number):
        """API search in separate thread"""
        try:
            url = f"{self.api_base_url}{passport_number}"
            print(f"[MATCH TAB] Searching passport: {passport_number}")
            print(f"[MATCH TAB] API URL: {url}")
            print(f"[MATCH TAB] Base URL: {self.api_base_url}")
            print(f"[MATCH TAB] Fingerprint lookup URL: {self.fingerprint_lookup_url}")
            
            response = requests.get(url, timeout=10)
            print(f"[MATCH TAB] Response status: {response.status_code}")
            print(f"[MATCH TAB] Response headers: {dict(response.headers)}")
            print(f"[MATCH TAB] Response text: {response.text}")
            
            # Schedule UI update in main thread
            self.root.after(0, self._handle_match_api_response, response, passport_number)
            
        except requests.exceptions.RequestException as e:
            print(f"[MATCH TAB] Request exception: {str(e)}")
            self.root.after(0, self._handle_match_api_error, str(e))
            
    def _handle_match_api_response(self, response, passport_number):
        """Handle API response in main thread"""
        try:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.current_match_user_data = data.get('data')
                    self._display_match_user_details(self.current_match_user_data)
                    self.match_loading_label.configure(text="User found successfully!", style='Success.TLabel')
                else:
                    self._handle_match_api_error(data.get('message', 'Unknown error'))
            else:
                self._handle_match_api_error(f"HTTP {response.status_code}: {response.text}")
                
        except json.JSONDecodeError:
            self._handle_match_api_error("Invalid response format")
        except Exception as e:
            self._handle_match_api_error(str(e))
        finally:
            self.match_search_btn.configure(state='normal')
            
    def _handle_match_api_error(self, error_message):
        """Handle API errors"""
        self.match_loading_label.configure(text=f"Error: {error_message}", style='Error.TLabel')
        self.match_search_btn.configure(state='normal')
        self.match_details_frame.pack_forget()
        self.current_match_user_data = None
        
    def _display_match_user_details(self, user_data):
        """Display user details with left (details) and right (photo/emoji) layout"""
        for widget in self.match_details_frame.winfo_children():
            widget.destroy()
        self.match_details_frame.pack(fill='x', pady=(0, 20))
        details_container, _ = self._build_details_with_photo(self.match_details_frame, user_data, is_match_tab=True)
        self._fill_detail_sections(details_container, user_data)

def main():
    root = tk.Tk()
    app = FingerprintApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
