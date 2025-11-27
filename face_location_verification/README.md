# Face & Location Verification Plugin for CTFd

A comprehensive security plugin for CTFd that requires users (including administrators) to capture their face and location before accessing challenges and other protected endpoints.

## Features

### Core Functionality

- **Face Capture**: Users must capture their face once using their device camera. The captured image is stored securely in the database.
- **Location Capture**: Users must allow and capture their location once. Location coordinates (latitude/longitude) are stored in the database.
- **Universal Verification**: All users, including administrators, must complete face and location verification before accessing any protected endpoints.
- **IP Change Detection**: If a user's IP address changes after initial verification, they are required to re-capture both face and location. The IP change is logged with the previous IP address.
- **Historical Logging**: All verification actions, IP changes, and captures are logged in the admin panel with timestamps, IP addresses, and user information.
- **Image Preservation**: When IP changes occur, old face images are preserved (not overwritten) with unique filenames that include username, user ID, IP hash, and timestamp.

### Security Features

- **Comprehensive Endpoint Protection**: All authenticated endpoints (web and API) require verification, except:
  - Authentication endpoints (login, register, password reset)
  - Static assets (CSS, JS, images)
  - Setup and healthcheck endpoints
  - Scoreboard (configurable - can be public or require verification)
- **Admin-Only Image Access**: Only administrators can view captured face images through a secure endpoint.
- **Unique Image Filenames**: Images are saved with unique filenames (`face_{username}_{user_id}_{ip_hash}_{timestamp}.jpg`) to prevent overwriting.
- **Reset CTFd Disabled**: The "Reset CTFd" feature in the admin panel is completely disabled for security.
- **Secure File Handling**:
  - Image validation (PIL or magic bytes)
  - File size limits (10MB max)
  - Automatic image resizing (max 2000px)
  - Metadata stripping
  - Restricted file permissions (0o600)
  - Path traversal protection
- **Input Validation**: All inputs are validated and sanitized to prevent injection attacks.
- **XSS Protection**: Client-side JavaScript uses safe DOM manipulation methods, and templates use auto-escaping.

### Admin Features

- **User Management**: View all users and their verification status, including admin status.
- **Verification Logs**: View detailed logs of all verification actions, including:
  - Face captures
  - Location captures
  - Verification completions
  - IP address changes
  - Previous IP addresses
- **Admin Status Display**: See which users are administrators in both the users table and logs table.
- **Image Viewing**: Administrators can view captured face images securely.

### Configuration

- **Scoreboard Visibility**: Configure whether the scoreboard requires verification or is publicly accessible:
  - `face_location_scoreboard_require_verification = "true"`: Scoreboard requires verification (default)
  - `face_location_scoreboard_require_verification = "false"`: Scoreboard is publicly accessible

## Installation

1. Place the plugin folder in `CTFd/plugins/face_location_verification/`
2. Restart CTFd
3. The plugin will automatically create the necessary database tables

## Database Schema

### `face_location_verification` Table

- `id`: Primary key
- `user_id`: Foreign key to users table (unique)
- `face_image_path`: Relative path to stored face image
- `latitude`: Location latitude
- `longitude`: Location longitude
- `ip_address`: IP address used during verification
- `captured_at`: Timestamp of first capture
- `updated_at`: Timestamp of last update

### `face_location_log` Table

- `id`: Primary key
- `user_id`: Foreign key to users table
- `ip_address`: IP address at time of action
- `previous_ip`: Previous IP address (for IP change tracking)
- `action`: Action type (face_captured, location_captured, verification_complete, ip_changed, etc.)
- `face_image_path`: Path to face image (if applicable)
- `latitude`: Location latitude (if applicable)
- `longitude`: Location longitude (if applicable)
- `created_at`: Timestamp of the log entry

## Security Considerations

1. **Privacy**: Face images and location data are sensitive. Ensure proper access controls and data protection measures are in place.
2. **GDPR Compliance**: Consider data retention policies and user consent requirements.
3. **File Storage**: Face images are stored in the CTFd uploads directory. Ensure proper backup and access controls.
4. **IP Address Tracking**: IP addresses are logged for security purposes. Be aware of privacy implications.
5. **Rate Limiting**: Consider implementing rate limiting for capture endpoints in high-traffic scenarios.

## Technical Details

- **Image Processing**: Uses PIL (Pillow) if available, with fallback to magic byte validation
- **File Format**: Images are converted to JPEG format with metadata stripped
- **Image Size**: Automatically resized if larger than 2000x2000 pixels
- **File Permissions**: Images are stored with 0o600 permissions (owner read/write only)
- **Database**: Uses SQLAlchemy ORM with proper parameterized queries
- **Templates**: Uses Jinja2 with auto-escaping enabled
- **JavaScript**: Uses safe DOM manipulation (createElement, createTextNode) to prevent XSS

## API Endpoints

- `GET /face-location/verification`: Display verification page
- `POST /face-location/capture-face`: Capture face image (JSON)
- `POST /face-location/capture-location`: Capture location (JSON)
- `GET /face-location/face-image/<filename>`: Get face image (admin only)
- `GET /face-location/admin/users`: Admin - View all users
- `GET /face-location/admin/logs`: Admin - View verification logs

## Requirements

- CTFd 3.x
- Python 3.7+
- PIL/Pillow (optional, for image validation and processing)

## License

This plugin is provided as-is for use with CTFd.
