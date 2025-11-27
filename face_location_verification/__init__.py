import base64
import datetime
import json
import os
import re
import secrets
from io import BytesIO

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

# Try to import PIL for image validation, but make it optional
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from CTFd.models import Users, db
from sqlalchemy.orm import joinedload
from CTFd.plugins import register_plugin_assets_directory, bypass_csrf_protection
from CTFd.utils.decorators import authed_only, admins_only
from CTFd.utils.logging import log
from CTFd.utils.user import get_current_user, get_ip, is_admin, authed
from CTFd.utils import validators
import math
import hashlib

# Try to import cryptography library for AES-GCM decryption
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    print("Warning: cryptography library not available. Encryption will use fallback method.")

# Create Blueprint for plugin routes
face_location_bp = Blueprint(
    "face_location_verification", __name__, url_prefix="/face-location"
)


# Database Models
class FaceLocationVerification(db.Model):
    __tablename__ = "face_location_verification"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    face_image_path = db.Column(db.Text, nullable=True)  # Path to stored face image
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    ip_address = db.Column(db.String(46), nullable=True)
    captured_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = db.relationship("Users", foreign_keys="FaceLocationVerification.user_id", lazy="select")

    def __init__(self, user_id, face_image_path=None, latitude=None, longitude=None, ip_address=None):
        self.user_id = user_id
        self.face_image_path = face_image_path
        self.latitude = latitude
        self.longitude = longitude
        self.ip_address = ip_address

    def __repr__(self):
        return f"<FaceLocationVerification user_id={self.user_id}>"

    @property
    def is_complete(self):
        """Check if both face and location are captured"""
        return self.face_image_path is not None and self.latitude is not None and self.longitude is not None


class FaceLocationLog(db.Model):
    """Admin log for face and location captures"""
    __tablename__ = "face_location_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    ip_address = db.Column(db.String(46))
    action = db.Column(db.String(50))  # 'face_captured', 'location_captured', 'verification_complete', 'ip_changed'
    face_image_path = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    previous_ip = db.Column(db.String(46), nullable=True)  # For IP change tracking
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    user = db.relationship("Users", foreign_keys="FaceLocationLog.user_id", lazy="select")

    def __init__(self, user_id, ip_address, action, face_image_path=None, latitude=None, longitude=None, previous_ip=None):
        self.user_id = user_id
        self.ip_address = ip_address
        self.action = action
        self.face_image_path = face_image_path
        self.latitude = latitude
        self.longitude = longitude
        self.previous_ip = previous_ip

    def __repr__(self):
        return f"<FaceLocationLog user_id={self.user_id} action={self.action}>"


# Helper Functions
def get_user_verification(user_id, refresh=False):
    """Get verification record for a user"""
    # Validate user_id is an integer to prevent SQL injection
    if not isinstance(user_id, int) or user_id < 1:
        return None
    verification = FaceLocationVerification.query.filter_by(user_id=user_id).first()
    if verification and refresh:
        # Refresh from database to get latest data
        db.session.refresh(verification)
    return verification


def is_user_verified(user_id, current_ip=None):
    """Check if user has completed face and location verification and IP matches"""
    # Validate user_id is an integer to prevent SQL injection
    if not isinstance(user_id, int) or user_id < 1:
        return False
    verification = get_user_verification(user_id)
    if verification is None or not verification.is_complete:
        return False
    
    # Check if IP address has changed - if so, require re-verification
    if current_ip and verification.ip_address:
        if verification.ip_address != current_ip:
            # IP changed - log it with previous IP and OLD image path (preserve old logs and images)
            # Store the current (old) image path before we potentially update it
            old_image_path = verification.face_image_path
            try:
                log_entry = FaceLocationLog(
                    user_id=user_id,
                    ip_address=current_ip,
                    action="ip_changed",
                    face_image_path=old_image_path,  # Keep reference to old image
                    latitude=verification.latitude,
                    longitude=verification.longitude,
                    previous_ip=verification.ip_address
                )
                db.session.add(log_entry)
                db.session.commit()
            except Exception as e:
                # If previous_ip column doesn't exist, try without it
                if "previous_ip" in str(e).lower() or "unknown column" in str(e).lower():
                    try:
                        log_entry = FaceLocationLog(
                            user_id=user_id,
                            ip_address=current_ip,
                            action="ip_changed",
                            face_image_path=verification.face_image_path,
                            latitude=verification.latitude,
                            longitude=verification.longitude
                        )
                        db.session.add(log_entry)
                        db.session.commit()
                    except:
                        db.session.rollback()
                else:
                    db.session.rollback()
            
            # IMPORTANT: When IP changes, require BOTH face and location re-capture
            # Keep old image path in database for history, but clear it to force re-capture
            # The old face_image_path is already saved in the log above
            # Clear both face and location to force complete re-verification
            old_face_path = verification.face_image_path  # Keep reference to old image (already logged)
            verification.face_image_path = None  # Clear to force face re-capture
            verification.latitude = None  # Clear to force location re-capture
            verification.longitude = None  # Clear to force location re-capture
            # Don't update IP yet - keep old IP for reference, update after re-verification
            verification.updated_at = datetime.datetime.utcnow()
            db.session.commit()
            # Return False immediately to require re-verification (both face and location)
            # Old image is preserved in the log entry created above
            return False
    
    # Double-check is_complete after potential IP change
    if not verification.is_complete:
        return False
    
    return True


def log_verification_action(user_id, ip_address, action, face_image_path=None, latitude=None, longitude=None, previous_ip=None):
    """Log verification action to admin log"""
    # Validate inputs to prevent injection and ensure data integrity
    if not isinstance(user_id, int) or user_id < 1:
        return  # Invalid user_id, skip logging
    if not isinstance(ip_address, str) or len(ip_address) > 46:
        ip_address = str(ip_address)[:46] if ip_address else None
    if not isinstance(action, str) or len(action) > 50:
        action = str(action)[:50] if action else "unknown"
    if previous_ip and (not isinstance(previous_ip, str) or len(previous_ip) > 46):
        previous_ip = str(previous_ip)[:46] if previous_ip else None
    
    log_entry = FaceLocationLog(
        user_id=user_id,
        ip_address=ip_address,
        action=action,
        face_image_path=face_image_path,
        latitude=latitude,
        longitude=longitude,
        previous_ip=previous_ip
    )
    db.session.add(log_entry)
    db.session.commit()
    
    # Also log to CTFd's logging system
    # The log function formats and logs the message automatically
    # Note: log() doesn't return a logger, it logs internally
    try:
        log("face_location_verification", 
            "User {id} ({action}) from IP {ip} at {date}",
            action=action)
    except Exception as e:
        # If logging fails, don't break the flow
        print(f"Warning: Could not log to CTFd logging system: {e}")


# Decorator to require verification
def require_face_location_verification(f):
    """Decorator that requires users to have completed face and location verification (including admins)"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # NO ADMIN EXEMPTION - all users including admins must verify
        if not authed():
            if request.content_type == "application/json":
                return jsonify({"success": False, "message": "Authentication required"}), 403
            return redirect(url_for("auth.login", next=request.full_path))
        
        user = get_current_user()
        current_ip = get_ip()
        if not is_user_verified(user.id, current_ip=current_ip):
            # Redirect to verification page
            if request.content_type == "application/json":
                return jsonify({
                    "success": False,
                    "message": "Face and location verification required",
                    "redirect": url_for("face_location_verification.verification_page")
                }), 403
            return redirect(url_for("face_location_verification.verification_page"))
        
        return f(*args, **kwargs)
    
    return decorated_function


# Routes
@face_location_bp.route("/verification", methods=["GET"])
@authed_only
def verification_page():
    """Display verification page where users capture face and location"""
    user = get_current_user()
    current_ip = get_ip()
    
    # IMPORTANT: Check verification status with current IP FIRST
    # This will clear face_image_path, latitude, and longitude if IP changed
    is_verified = is_user_verified(user.id, current_ip=current_ip)
    
    # Refresh verification from database after IP check (data may have been cleared)
    # Need to refresh the session to get updated data
    db.session.expire_all()
    verification = get_user_verification(user.id, refresh=True)
    
    # Double-check: if verification exists but IP doesn't match, force re-capture
    # This is a safety check in case is_user_verified() didn't catch it
    if verification and verification.ip_address and verification.ip_address != current_ip:
        # IP mismatch detected - log and clear everything to force re-capture
        try:
            log_entry = FaceLocationLog(
                user_id=user.id,
                ip_address=current_ip,
                action="ip_changed",
                face_image_path=verification.face_image_path,
                latitude=verification.latitude,
                longitude=verification.longitude,
                previous_ip=verification.ip_address
            )
            db.session.add(log_entry)
        except:
            pass  # If logging fails, continue anyway
        
        # Clear everything to force re-capture
        verification.face_image_path = None
        verification.latitude = None
        verification.longitude = None
        db.session.commit()
        
        # Refresh again after commit to get updated None values
        db.session.refresh(verification)
    
    # Check if face and location are captured (after potential IP change clearing)
    # If IP changed, face_image_path should be None now
    face_captured = verification is not None and verification.face_image_path is not None
    location_captured = verification is not None and verification.latitude is not None
    
    # Generate encryption key and IV for this session (end-to-end encryption)
    # Key is 32 bytes (256 bits) for AES-256-GCM
    encryption_key = secrets.token_bytes(32)
    # IV is 12 bytes (96 bits) for AES-GCM
    encryption_iv = secrets.token_bytes(12)
    
    # Store in session for decryption (session-based, not persistent)
    from flask import session
    session['face_location_encryption_key'] = base64.b64encode(encryption_key).decode('utf-8')
    session['face_location_encryption_iv'] = base64.b64encode(encryption_iv).decode('utf-8')
    
    # Pass to template for client-side encryption
    encryption_key_b64 = base64.b64encode(encryption_key).decode('utf-8')
    encryption_iv_b64 = base64.b64encode(encryption_iv).decode('utf-8')
    
    # Plugin templates use "plugins/" prefix, then path relative to plugin root
    return render_template(
        "plugins/face_location_verification/templates/face_location_verification/verification.html",
        face_captured=face_captured,
        location_captured=location_captured,
        verification_complete=is_verified,
        verification=verification,
        user_id=user.id,
        current_user_ip=current_ip,
        encryption_key=encryption_key_b64,
        encryption_iv=encryption_iv_b64
    )


@face_location_bp.route("/capture-face", methods=["POST"])
@bypass_csrf_protection
def capture_face():
    """Handle face capture submission with end-to-end decryption"""
    # Check authentication manually to return proper JSON error
    if not authed():
        return jsonify({"success": False, "message": "Authentication required"}), 403
    
    user = get_current_user()
    
    # Check if already captured (allow re-capture if IP changed or data is None)
    verification = get_user_verification(user.id)
    current_ip = get_ip()
    if verification and verification.face_image_path:
        # Allow re-capture if IP has changed (IP mismatch means re-verification needed)
        # If IP matches and face is already captured, prevent duplicate capture
        if verification.ip_address and verification.ip_address == current_ip:
            return jsonify({
                "success": False,
                "message": "Face already captured for this IP address. You can only capture once per IP address."
            }), 400
        # If IP changed, allow re-capture (face_image_path will be cleared by is_user_verified when IP changes)
    
    # Get encrypted data from request
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    
    # Decrypt the encrypted data
    try:
        from flask import session
        encryption_key_b64 = session.get('face_location_encryption_key')
        encryption_iv_b64 = session.get('face_location_encryption_iv')
        
        if not encryption_key_b64 or not encryption_iv_b64:
            return jsonify({"success": False, "message": "Encryption session expired. Please refresh the page."}), 400
        
        encryption_key = base64.b64decode(encryption_key_b64)
        encryption_iv = base64.b64decode(encryption_iv_b64)
        
        # Decrypt the encrypted payload
        if "encrypted" in data and "iv" in data:
            encrypted_data = base64.b64decode(data["encrypted"])
            
            if CRYPTOGRAPHY_AVAILABLE:
                # Use cryptography library for decryption
                aesgcm = AESGCM(encryption_key)
                decrypted_data = aesgcm.decrypt(encryption_iv, encrypted_data, None)
                decrypted_json = json.loads(decrypted_data.decode('utf-8'))
                image_data = decrypted_json.get("image")
            else:
                # Fallback: try to decode as base64 directly (for testing without cryptography lib)
                # In production, cryptography library should be installed
                try:
                    # If encrypted field exists but we can't decrypt, return error
                    return jsonify({"success": False, "message": "Decryption failed. Please install cryptography library."}), 500
                except:
                    return jsonify({"success": False, "message": "Decryption failed."}), 500
        else:
            # Legacy support: if not encrypted, use directly (for backward compatibility)
            if "image" not in data:
                return jsonify({"success": False, "message": "No image data provided"}), 400
            image_data = data["image"]
    except Exception as e:
        # Log error but don't expose details
        print(f"Decryption error: {e}")
        return jsonify({"success": False, "message": "Failed to decrypt data. Please try again."}), 400
    
    if not image_data:
        return jsonify({"success": False, "message": "No image data provided"}), 400
    
    # Validate image_data is a string
    if not isinstance(image_data, str):
        return jsonify({"success": False, "message": "Invalid image data format"}), 400
    
    # Remove data URL prefix if present
    if "," in image_data:
        image_data = image_data.split(",")[1]
    
    # Validate base64 string length (prevent extremely large payloads)
    if len(image_data) > 10 * 1024 * 1024:  # 10MB limit
        return jsonify({"success": False, "message": "Image too large. Maximum size is 10MB."}), 400
    
    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_data, validate=True)
        
        # Validate decoded size (prevent memory exhaustion)
        if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
            return jsonify({"success": False, "message": "Image too large. Maximum size is 10MB."}), 400
        
        # Validate that it's actually an image by trying to open it with PIL (if available)
        if PIL_AVAILABLE:
            try:
                img = Image.open(BytesIO(image_bytes))
                # Verify it's a valid image format
                img.verify()
                # Reopen after verify (verify closes the image)
                img = Image.open(BytesIO(image_bytes))
                # Convert to RGB if necessary (security: strip metadata)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Resize if too large (prevent DoS)
                max_dimension = 2000
                if img.width > max_dimension or img.height > max_dimension:
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                # Save to bytes
                output = BytesIO()
                img.save(output, format='JPEG', quality=85, optimize=True)
                image_bytes = output.getvalue()
            except Exception as img_error:
                return jsonify({"success": False, "message": "Invalid image format. Please upload a valid image."}), 400
        else:
            # Basic validation if PIL is not available: check for JPEG/PNG magic bytes
            if len(image_bytes) < 4:
                return jsonify({"success": False, "message": "Invalid image data"}), 400
            # Check for JPEG magic bytes (FF D8 FF) or PNG magic bytes (89 50 4E 47)
            if not (image_bytes[:3] == b'\xff\xd8\xff' or image_bytes[:4] == b'\x89PNG'):
                return jsonify({"success": False, "message": "Invalid image format. Only JPEG and PNG images are supported."}), 400
        
        # Get CTFd upload folder from config
        from flask import current_app
        upload_base = current_app.config.get("UPLOAD_FOLDER")
        if not upload_base:
            # Fallback to default location
            upload_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
        
        # Save image to uploads directory with unique filename (include IP hash to prevent overwrites)
        upload_folder = os.path.join(upload_base, "face_captures")
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create unique filename with username, user_id, IP hash, and timestamp to prevent overwriting old images
        # Sanitize username for filename (remove special characters, prevent path traversal)
        safe_username = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in str(user.name))[:50]
        # Additional sanitization: remove any remaining dangerous characters
        safe_username = re.sub(r'[^a-zA-Z0-9_-]', '_', safe_username)
        
        # Validate user.id is an integer
        if not isinstance(user.id, int) or user.id < 1:
            return jsonify({"success": False, "message": "Invalid user ID"}), 400
        
        ip_hash = hashlib.md5(current_ip.encode()).hexdigest()[:8] if current_ip else "unknown"
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"face_{safe_username}_{user.id}_{ip_hash}_{timestamp}.jpg"
        
        # Additional filename validation (prevent path traversal)
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({"success": False, "message": "Invalid filename"}), 400
        
        filepath = os.path.join(upload_folder, filename)
        
        # Ensure filepath is within upload_folder (prevent path traversal)
        filepath = os.path.normpath(filepath)
        upload_folder_norm = os.path.normpath(upload_folder)
        if not filepath.startswith(upload_folder_norm):
            return jsonify({"success": False, "message": "Invalid file path"}), 400
        
        # Write file with restricted permissions (owner read/write only)
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        
        # Set file permissions (owner read/write only)
        try:
            os.chmod(filepath, 0o600)
        except OSError:
            pass  # If chmod fails, continue anyway
        
        # Store relative path
        relative_path = f"face_captures/{filename}"
        
        # Get current IP
        current_ip = get_ip()
        previous_ip = verification.ip_address if verification else None
        old_face_path = verification.face_image_path if verification else None
        
        # Create or update verification record
        if verification is None:
            verification = FaceLocationVerification(
                user_id=user.id,
                face_image_path=relative_path,
                ip_address=current_ip
            )
            db.session.add(verification)
        else:
            # If IP changed and there's an old image, log it before updating
            if previous_ip and previous_ip != current_ip and old_face_path:
                # Log the old image path before replacing (old image file stays on disk)
                try:
                    log_entry = FaceLocationLog(
                        user_id=user.id,
                        ip_address=previous_ip,
                        action="face_image_archived",
                        face_image_path=old_face_path,
                        latitude=verification.latitude,
                        longitude=verification.longitude,
                        previous_ip=None
                    )
                    db.session.add(log_entry)
                except:
                    pass  # If logging fails, continue anyway
            
            # Update with new image path (old image file is still on disk with different filename)
            verification.face_image_path = relative_path
            verification.ip_address = current_ip
            verification.updated_at = datetime.datetime.utcnow()
            
            # If IP changed, log it
            if previous_ip and previous_ip != current_ip:
                try:
                    log_entry = FaceLocationLog(
                        user_id=user.id,
                        ip_address=current_ip,
                        action="ip_changed_during_capture",
                        face_image_path=relative_path,
                        previous_ip=previous_ip
                    )
                    db.session.add(log_entry)
                except Exception as e:
                    # If previous_ip column doesn't exist, try without it
                    if "previous_ip" in str(e).lower() or "unknown column" in str(e).lower():
                        try:
                            log_entry = FaceLocationLog(
                                user_id=user.id,
                                ip_address=current_ip,
                                action="ip_changed_during_capture",
                                face_image_path=relative_path
                            )
                            db.session.add(log_entry)
                        except:
                            pass  # Skip logging if it fails
        
        db.session.commit()
        
        # Log the action
        log_verification_action(
            user.id,
            get_ip(),
            "face_captured",
            face_image_path=relative_path
        )
        
        return jsonify({
            "success": True,
            "message": "Face captured successfully"
        })
    
    except (ValueError, TypeError) as e:
        # Invalid input errors
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": "Invalid image data provided"
        }), 400
    except Exception as e:
        # Generic error - don't expose internal details
        db.session.rollback()
        # Log error for debugging but don't expose to user
        print(f"Error saving face image: {e}")
        return jsonify({
            "success": False,
            "message": "An error occurred while saving the image. Please try again."
        }), 500


@face_location_bp.route("/capture-location", methods=["POST"])
@bypass_csrf_protection
def capture_location():
    """Handle location capture submission with end-to-end decryption"""
    # Check authentication manually to return proper JSON error
    if not authed():
        return jsonify({"success": False, "message": "Authentication required"}), 403
    
    user = get_current_user()
    
    # Check if already captured (allow re-capture if IP changed or data is None)
    verification = get_user_verification(user.id)
    current_ip = get_ip()
    if verification and verification.latitude is not None:
        # Allow re-capture if IP has changed (IP mismatch means re-verification needed)
        # If IP matches and location is already captured, prevent duplicate capture
        if verification.ip_address and verification.ip_address == current_ip:
            return jsonify({
                "success": False,
                "message": "Location already captured for this IP address. You can only capture once per IP address."
            }), 400
        # If IP changed, allow re-capture (latitude/longitude will be cleared by is_user_verified when IP changes)
    
    # Get encrypted data from request
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    
    # Decrypt the encrypted data
    try:
        from flask import session
        encryption_key_b64 = session.get('face_location_encryption_key')
        encryption_iv_b64 = session.get('face_location_encryption_iv')
        
        if not encryption_key_b64 or not encryption_iv_b64:
            return jsonify({"success": False, "message": "Encryption session expired. Please refresh the page."}), 400
        
        encryption_key = base64.b64decode(encryption_key_b64)
        encryption_iv = base64.b64decode(encryption_iv_b64)
        
        # Decrypt the encrypted payload
        if "encrypted" in data and "iv" in data:
            encrypted_data = base64.b64decode(data["encrypted"])
            
            if CRYPTOGRAPHY_AVAILABLE:
                # Use cryptography library for decryption
                aesgcm = AESGCM(encryption_key)
                decrypted_data = aesgcm.decrypt(encryption_iv, encrypted_data, None)
                decrypted_json = json.loads(decrypted_data.decode('utf-8'))
                latitude = float(decrypted_json.get("latitude"))
                longitude = float(decrypted_json.get("longitude"))
            else:
                # Fallback: try to decode as base64 directly (for testing without cryptography lib)
                # In production, cryptography library should be installed
                try:
                    # If encrypted field exists but we can't decrypt, return error
                    return jsonify({"success": False, "message": "Decryption failed. Please install cryptography library."}), 500
                except:
                    return jsonify({"success": False, "message": "Decryption failed."}), 500
        else:
            # Legacy support: if not encrypted, use directly (for backward compatibility)
            if "latitude" not in data or "longitude" not in data:
                return jsonify({"success": False, "message": "Location data not provided"}), 400
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
    except Exception as e:
        # Log error but don't expose details
        print(f"Decryption error: {e}")
        return jsonify({"success": False, "message": "Failed to decrypt data. Please try again."}), 400
    
    # Validate and convert coordinates with error handling
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid coordinate format"}), 400
    
    # Validate coordinates are within valid ranges
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return jsonify({"success": False, "message": "Invalid coordinate type"}), 400
    
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return jsonify({"success": False, "message": "Invalid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180."}), 400
    
    # Check for NaN or Infinity values
    if math.isnan(latitude) or math.isnan(longitude) or math.isinf(latitude) or math.isinf(longitude):
        return jsonify({"success": False, "message": "Invalid coordinate values"}), 400
    
    try:
        # Get current IP
        current_ip = get_ip()
        previous_ip = verification.ip_address if verification else None
        
        # Create or update verification record
        if verification is None:
            verification = FaceLocationVerification(
                user_id=user.id,
                latitude=latitude,
                longitude=longitude,
                ip_address=current_ip
            )
            db.session.add(verification)
        else:
            verification.latitude = latitude
            verification.longitude = longitude
            # Update IP address when location is captured (re-verification after IP change)
            verification.ip_address = current_ip
            verification.updated_at = datetime.datetime.utcnow()
            
            # If IP changed, log it
            if previous_ip and previous_ip != current_ip:
                try:
                    log_entry = FaceLocationLog(
                        user_id=user.id,
                        ip_address=current_ip,
                        action="ip_changed_during_capture",
                        latitude=latitude,
                        longitude=longitude,
                        previous_ip=previous_ip
                    )
                    db.session.add(log_entry)
                except Exception as e:
                    # If previous_ip column doesn't exist, try without it
                    if "previous_ip" in str(e).lower() or "unknown column" in str(e).lower():
                        try:
                            log_entry = FaceLocationLog(
                                user_id=user.id,
                                ip_address=current_ip,
                                action="ip_changed_during_capture",
                                latitude=latitude,
                                longitude=longitude
                            )
                            db.session.add(log_entry)
                        except:
                            pass  # Skip logging if it fails
        
        db.session.commit()
        
        # Log the action
        log_verification_action(
            user.id,
            get_ip(),
            "location_captured",
            latitude=latitude,
            longitude=longitude
        )
        
        # Check if verification is now complete
        if verification.is_complete:
            log_verification_action(
                user.id,
                get_ip(),
                "verification_complete",
                face_image_path=verification.face_image_path,
                latitude=latitude,
                longitude=longitude
            )
        
        return jsonify({
            "success": True,
            "message": "Location captured successfully",
            "verification_complete": verification.is_complete
        })
    
    except (ValueError, TypeError) as e:
        # Invalid input errors
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": "Invalid location data provided"
        }), 400
    except Exception as e:
        # Generic error - don't expose internal details
        db.session.rollback()
        # Log error for debugging but don't expose to user
        print(f"Error saving location: {e}")
        return jsonify({
            "success": False,
            "message": "An error occurred while saving the location. Please try again."
        }), 500


@face_location_bp.route("/face-image/<path:filename>", methods=["GET"])
@admins_only
def get_face_image(filename):
    """Get face image by filename (admin only)"""
    # Only admins can view face images
    if not is_admin():
        return jsonify({"success": False, "message": "Unauthorized. Admin access required."}), 403
    
    # Validate filename format: face_{username}_{user_id}_{ip_hash}_{timestamp}.jpg
    # Additional security: validate filename doesn't contain path traversal or dangerous characters
    if not isinstance(filename, str):
        return jsonify({"success": False, "message": "Invalid filename type"}), 400
    
    # Check for path traversal attempts
    if '..' in filename or '/' in filename or '\\' in filename or filename.startswith('.'):
        return jsonify({"success": False, "message": "Invalid filename format"}), 400
    
    # Validate filename format: face_{username}_{user_id}_{ip_hash}_{timestamp}.jpg
    if not filename.startswith("face_") or not filename.endswith(".jpg"):
        return jsonify({"success": False, "message": "Invalid filename format"}), 400
    
    # Validate filename length (prevent extremely long filenames)
    if len(filename) > 255:
        return jsonify({"success": False, "message": "Filename too long"}), 400
    
    # Validate filename contains only safe characters
    if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        return jsonify({"success": False, "message": "Invalid filename characters"}), 400
    
    # Get full path using CTFd upload folder
    from flask import current_app
    upload_base = current_app.config.get("UPLOAD_FOLDER")
    if not upload_base:
        # Fallback to default location
        upload_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
    
    # Construct file path - always use face_captures subdirectory
    filepath = os.path.join(upload_base, "face_captures", filename)
    
    # Security: Ensure the file is within the upload directory (prevent path traversal)
    filepath = os.path.normpath(filepath)
    upload_base = os.path.normpath(upload_base)
    expected_prefix = os.path.normpath(os.path.join(upload_base, "face_captures"))
    if not filepath.startswith(expected_prefix):
        return jsonify({"success": False, "message": "Invalid file path"}), 403
    
    if not os.path.exists(filepath):
        return jsonify({"success": False, "message": "Image file not found"}), 404
    
    # Additional security: verify it's actually a file (not a directory)
    if not os.path.isfile(filepath):
        return jsonify({"success": False, "message": "Invalid file"}), 403
    
    # Set secure headers
    response = send_file(filepath, mimetype="image/jpeg")
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
    return response


# Admin routes
@face_location_bp.route("/admin/logs", methods=["GET"])
@admins_only
def admin_logs():
    """Admin page to view verification logs"""
    
    # Query logs with user relationship joined to avoid N+1 queries
    # Limit to 100 records to prevent DoS
    try:
        logs = FaceLocationLog.query.options(
            joinedload(FaceLocationLog.user)
        ).order_by(FaceLocationLog.created_at.desc()).limit(100).all()
    except Exception as e:
        # If query fails, return empty list
        print(f"Error querying logs: {e}")
        logs = []
    
    # Add admin status for each log entry
    log_data = []
    for log in logs:
        # Check if user exists and is admin
        is_admin = False
        try:
            if log.user:
                is_admin = log.user.type == "admin" if hasattr(log.user, 'type') and log.user.type else False
        except Exception as e:
            # If user relationship fails, skip admin check
            print(f"Error checking admin status for log {log.id}: {e}")
            is_admin = False
        
        log_data.append({
            "log": log,
            "is_admin": is_admin
        })
    
    # Plugin templates use "plugins/" prefix, then path relative to plugin root
    return render_template("plugins/face_location_verification/templates/face_location_verification/admin_logs.html", log_data=log_data)


@face_location_bp.route("/admin/users", methods=["GET"])
@admins_only
def admin_users():
    """Admin page to view all users and their verification status"""
    
    # Query all users (admin only endpoint, so this is acceptable)
    # In production, consider pagination for large user bases
    users = Users.query.all()
    user_verifications = {}
    
    for user in users:
        # Validate user.id before querying
        if not isinstance(user.id, int) or user.id < 1:
            continue  # Skip invalid user IDs
        verification = get_user_verification(user.id)
        # Check if user is admin
        user_is_admin = user.type == "admin" if hasattr(user, 'type') else False
        user_verifications[user.id] = {
            "verification": verification,
            "is_complete": verification.is_complete if verification else False,
            "is_admin": user_is_admin
        }
    
    # Plugin templates use "plugins/" prefix, then path relative to plugin root
    return render_template(
        "plugins/face_location_verification/templates/face_location_verification/admin_users.html",
        users=users,
        user_verifications=user_verifications
    )


def load(app):
    """Main plugin load function"""
    # Create database tables
    app.db.create_all()
    
    # Run plugin migrations to add previous_ip column if needed
    try:
        from CTFd.plugins.migrations import upgrade as plugin_upgrade
        plugin_upgrade(plugin_name="face_location_verification")
    except Exception as e:
        # Migration might fail if column already exists or migration system not available
        # This is fine, we'll handle it gracefully in the code
        print(f" * Note: Could not run plugin migrations: {e}")
        pass
    
    # The before_request hook will handle IP checking on every request
    # This ensures IP changes are detected even after login
    
    # Register blueprint
    app.register_blueprint(face_location_bp)
    
    # Register assets directory
    register_plugin_assets_directory(
        app,
        base_path="/plugins/face_location_verification/assets/"
    )
    
    # Block reset endpoint FIRST (before verification check)
    # This ensures reset is blocked even without verification
    @app.before_request
    def block_reset_endpoint():
        path = request.path or ""
        endpoint = request.endpoint or ""
        # Block both web and API reset endpoints
        if (path == "/admin/reset" or 
            path.startswith("/admin/reset") or
            endpoint == "admin.reset"):
            from flask import abort
            abort(404, description="Reset CTFd feature has been disabled")
        return None
    
    # Override challenges route to require verification
    # Get the original function from app.view_functions after it's been registered
    original_listing = app.view_functions.get("challenges.listing")
    
    if original_listing:
        # Store original function
        _original_challenges_listing = original_listing
        
        # Create a wrapper function that preserves the original
        def challenges_listing_wrapper(*args, **kwargs):
            # NO ADMIN EXEMPTION - all users including admins must verify
            if not authed():
                return redirect(url_for("auth.login", next=request.full_path))
            
            user = get_current_user()
            current_ip = get_ip()
            if user and not is_user_verified(user.id, current_ip=current_ip):
                return redirect(url_for("face_location_verification.verification_page"))
            
            return _original_challenges_listing(*args, **kwargs)
        
        # Override challenges view function
        app.view_functions["challenges.listing"] = challenges_listing_wrapper
        print(" * Overrode challenges.listing route with verification check (all users including admins)")
    
    # Add before_request hook to check verification for ALL endpoints
    # This must be registered early to run before other hooks
    @app.before_request
    def check_verification_for_all_endpoints():
        endpoint = request.endpoint or ""
        path = request.path or ""
        
        # IMPORTANT: Skip our verification routes FIRST (capture-face, capture-location, verification page, etc.)
        # This must be checked before the verification check to allow users to complete verification
        if (path.startswith("/face-location/") or 
            path.startswith("/face-location") or
            endpoint.startswith("face_location_verification.") or
            "face_location_verification" in endpoint):
            return None
        
        # Skip auth endpoints (login, register, logout, password reset, etc.)
        if (path.startswith("/auth/") or 
            path.startswith("/login") or
            path.startswith("/register") or
            path.startswith("/reset_password") or
            endpoint.startswith("auth.") or
            "auth" in endpoint.lower()):
            return None
        
        # Skip static assets and plugin assets
        if (path.startswith("/static/") or 
            path.startswith("/themes/") or 
            path.startswith("/plugins/") or
            path.startswith("/files/") or
            endpoint.startswith("static") or
            endpoint.startswith("views.themes")):
            return None
        
        # Skip setup and healthcheck endpoints
        if (path.startswith("/setup") or
            path.startswith("/healthcheck") or
            endpoint.startswith("views.setup") or
            endpoint.startswith("views.healthcheck")):
            return None
        
        # Check scoreboard config - if allowed for unauth, skip verification
        is_scoreboard = (
            "scoreboard" in endpoint.lower() or 
            "/scoreboard" in path.lower() or 
            "/api/v1/scoreboard" in path.lower() or
            path.lower().startswith("/scoreboard")
        )
        
        if is_scoreboard:
            from CTFd.utils import get_config
            scoreboard_require_verification = get_config("face_location_scoreboard_require_verification", default="true")
            if scoreboard_require_verification == "false":
                # Scoreboard is public, no verification needed (even for unauthenticated users)
                return None
        
        # Skip if not authenticated (let normal auth handle it)
        # But only for non-scoreboard endpoints (scoreboard with config=false already handled above)
        if not authed():
            return None
        
        # NO ADMIN EXEMPTION - ALL users including admins must verify
        # This includes admin endpoints, API endpoints, and all other endpoints
        user = get_current_user()
        if not user:
            return None
        
        # Get current IP for verification check
        current_ip = get_ip()
        
        # Check if user is verified (including IP check)
        user_verified = is_user_verified(user.id, current_ip=current_ip)
        
        if not user_verified:
            # For ALL endpoints (including admin), require verification
            # Return JSON error for API requests
            if (request.content_type == "application/json" or 
                request.is_json or 
                "/api/" in path or
                request.accept_mimetypes.best == "application/json"):
                from flask import jsonify
                return jsonify({
                    "success": False,
                    "message": "Face and location verification required. Please complete verification first.",
                    "redirect": url_for("face_location_verification.verification_page")
                }), 403
            
            # For non-API requests, redirect to verification page
            # Include next parameter to redirect back after verification
            verification_url = url_for("face_location_verification.verification_page")
            current_path = request.full_path or request.path
            
            # Don't redirect if already on verification page (prevent redirect loop)
            if current_path and not current_path.startswith("/face-location/verification"):
                # Validate next parameter to prevent open redirect vulnerability
                # Use CTFd's validators.is_safe_url instead of werkzeug
                if validators.is_safe_url(current_path):
                    # Add next parameter to redirect back after verification
                    return redirect(url_for("face_location_verification.verification_page", next=current_path))
            
            # Already on verification page or unsafe path, just redirect to verification
            return redirect(url_for("face_location_verification.verification_page"))
        
        return None
    
    # Remove/hide the Reset CTFd feature from admin panel
    # Override the reset route to return 404 (both GET and POST)
    original_reset = app.view_functions.get("admin.reset")
    if original_reset:
        def reset_disabled(*args, **kwargs):
            from flask import abort
            abort(404, description="Reset CTFd feature has been disabled")
        app.view_functions["admin.reset"] = reset_disabled
        print(" * Disabled Reset CTFd feature (web route and API)")
    
    # Add admin menu item
    from CTFd.plugins import register_admin_plugin_menu_bar
    register_admin_plugin_menu_bar(
        "Face & Location Verification",
        "/face-location/admin/users"
    )
    
    print(" * Loaded plugin: Face Location Verification (all users including admins must verify)")

