# Face & Location Verification Plugin

This CTFd plugin requires users to capture their face and location before they can access challenges.

## Features

- **Face Capture**: Users must capture their face using their device camera (one-time only)
- **Location Capture**: Users must allow location access and capture their current location (one-time only)
- **Verification Required**: Only users who have completed both face and location verification can access challenges
- **Admin Logging**: All verification actions are logged with IP addresses, timestamps, and user information
- **Admin Dashboard**: Admins can view all users' verification status and access logs

## Installation

1. Place this plugin in `CTFd/plugins/face_location_verification/`
2. Restart CTFd
3. The plugin will automatically create the necessary database tables

## Usage

### For Users

1. After logging in, users will be redirected to the verification page if they haven't completed verification
2. Users must:
   - Allow camera access and capture their face
   - Allow location access and capture their location
3. Once both are completed, users can access challenges

### For Admins

- Access the verification dashboard from the Plugins menu in the admin panel
- View all users and their verification status
- View detailed logs of all verification actions
- View captured face images and location coordinates

## Database Tables

The plugin creates two database tables:

1. **face_location_verification**: Stores user verification data (face image path, location coordinates, IP address)
2. **face_location_log**: Stores admin logs of all verification actions

## Security Notes

- Face images are stored in `CTFd/uploads/face_captures/`
- Location coordinates are stored in the database
- IP addresses are logged for all verification actions
- Only admins and the user themselves can view their own face image

## Requirements

- Modern browser with camera and geolocation API support
- HTTPS recommended for camera and location access (required by browsers)

