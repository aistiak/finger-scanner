# Fingerprint Registration Desktop Application

A modern desktop application built with Tkinter for fingerprint registration and matching with passport API integration.

driver link: https://drive.google.com/file/d/1dZt0E7uWD3Jk04P7e1wGfM_HEU7dW7up/view

## Features

### Register Tab
- **Passport Search**: Enter passport number and search via API
- **User Details Display**: Beautiful formatted display of user information
- **Fingerprint Registration**: Capture and store fingerprints linked to passport data

### Match Tab
- **Stored Fingerprints List**: View all registered fingerprints
- **Fingerprint Matching**: Match live fingerprint against stored templates
- **Real-time Results**: Instant match/no-match feedback

## API Integration

The application integrates with a passport service API:
- **Endpoint**: `http://localhost:4111/api/v1/service-request/passport/{passport_number}`
- **Method**: GET
- **Response**: JSON with user details including personal info, visa details, branch, and country information

## Installation

1. Install required dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure your fingerprint scanner is connected and drivers are installed

3. Run the application:
```bash
python main.py
```

## Usage

### Registration Process
1. Switch to "Register" tab
2. Enter passport number in the search field
3. Click "Search" to fetch user details from API
4. Review the displayed user information
5. Click "Register Fingerprint" to capture and store fingerprint
6. Follow on-screen instructions for fingerprint capture

### Matching Process
1. Switch to "Match" tab
2. Click "Refresh List" to see all stored fingerprints
3. Enter the Finger ID you want to match against
4. Click "Match Fingerprint"
5. Place finger on scanner when prompted
6. View match results

## Technical Details

- **GUI Framework**: Tkinter with ttk styling
- **Database**: SQLite for fingerprint storage
- **Fingerprint SDK**: pyzkfp (ZKTeco SDK wrapper)
- **API Client**: requests library
- **Threading**: Non-blocking UI with background operations

## File Structure

```
gui/
├── main.py              # Main application file
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Dependencies

- `requests==2.32.5` - HTTP client for API calls
- `pyzkfp==0.1.5` - Fingerprint scanner SDK
- `pillow==11.3.0` - Image processing
- `tkinter` - GUI framework (built-in with Python)

## Error Handling

The application includes comprehensive error handling for:
- Network connectivity issues
- API response errors
- Fingerprint scanner connection problems
- Database operations
- Invalid user inputs

## UI Features

- **Responsive Design**: Adapts to different screen sizes
- **Loading Indicators**: Visual feedback during operations
- **Scrollable Content**: Handles large amounts of user data
- **Status Messages**: Real-time feedback with color coding
- **Threading**: Prevents UI freezing during long operations
