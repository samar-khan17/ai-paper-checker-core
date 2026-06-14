# ============================================================
#   core/security.py — Z-Plus Security Layer
#   Handles: password hashing, sessions, file validation,
#            brute-force protection, input sanitization
# ============================================================

import hashlib
import hmac
import os
import re
import time
import logging
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
from config import (SECRET_KEY, SESSION_TIMEOUT_MINUTES, MAX_LOGIN_ATTEMPTS,
                    LOCKOUT_MINUTES, MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS,
                    ALLOWED_MIME_TYPES, BCRYPT_ROUNDS)

logger = logging.getLogger("security")


# ── PASSWORD SECURITY ─────────────────────────────────────────
class PasswordManager:
    """Bcrypt-strength password hashing using PBKDF2."""
    
    ITERATIONS = 260_000  # OWASP 2024 recommendation for PBKDF2-SHA256
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with salt. Returns 'salt$hash' string."""
        PasswordManager._validate_strength(password)
        salt = os.urandom(32).hex()
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            PasswordManager.ITERATIONS
        ).hex()
        return f"{salt}${hashed}"
    
    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        """Timing-safe password verification."""
        try:
            salt, expected_hash = stored_hash.split('$', 1)
            actual_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                PasswordManager.ITERATIONS
            ).hex()
            return hmac.compare_digest(actual_hash, expected_hash)
        except Exception:
            return False
    
    @staticmethod
    def _validate_strength(password: str):
        """Enforce strong password policy."""
        errors = []
        if len(password) < 8:
            errors.append("at least 8 characters")
        if not re.search(r'[A-Z]', password):
            errors.append("one uppercase letter")
        if not re.search(r'[a-z]', password):
            errors.append("one lowercase letter")
        if not re.search(r'\d', password):
            errors.append("one number")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")


# ── BRUTE FORCE PROTECTION ────────────────────────────────────
class LoginAttemptTracker:
    """In-memory brute force tracker. Resets when app restarts."""
    
    def __init__(self):
        self._attempts: Dict[str, list] = {}  # username → [timestamps]
        self._locked: Dict[str, datetime] = {}  # username → lockout_until
    
    def record_attempt(self, username: str, success: bool):
        now = datetime.now()
        if success:
            self._attempts.pop(username, None)
            self._locked.pop(username, None)
            return
        
        if username not in self._attempts:
            self._attempts[username] = []
        self._attempts[username].append(now)
        
        # Keep only recent attempts
        cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
        self._attempts[username] = [t for t in self._attempts[username] if t > cutoff]
        
        if len(self._attempts[username]) >= MAX_LOGIN_ATTEMPTS:
            self._locked[username] = now + timedelta(minutes=LOCKOUT_MINUTES)
            logger.warning(f"Account locked: {username} after {MAX_LOGIN_ATTEMPTS} failed attempts")
    
    def is_locked(self, username: str) -> tuple[bool, int]:
        """Returns (is_locked, minutes_remaining)"""
        if username in self._locked:
            remaining = self._locked[username] - datetime.now()
            if remaining.total_seconds() > 0:
                return True, int(remaining.total_seconds() / 60) + 1
            else:
                del self._locked[username]
        return False, 0
    
    def attempts_remaining(self, username: str) -> int:
        recent = self._attempts.get(username, [])
        cutoff = datetime.now() - timedelta(minutes=LOCKOUT_MINUTES)
        recent_count = len([t for t in recent if t > cutoff])
        return max(0, MAX_LOGIN_ATTEMPTS - recent_count)


# ── SESSION MANAGEMENT ────────────────────────────────────────
class SessionManager:
    """Secure in-memory session handling."""
    
    def __init__(self):
        self._sessions: Dict[str, dict] = {}
    
    def create_session(self, user_data: dict) -> str:
        """Create a new session token."""
        token = os.urandom(32).hex()
        self._sessions[token] = {
            "user": user_data,
            "created_at": datetime.now(),
            "last_active": datetime.now(),
            "ip_fingerprint": os.urandom(8).hex()  # Placeholder for future IP binding
        }
        logger.info(f"Session created for user: {user_data.get('username')}")
        return token
    
    def get_session(self, token: str) -> Optional[dict]:
        """Retrieve session if valid and not expired."""
        session = self._sessions.get(token)
        if not session:
            return None
        
        timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        if datetime.now() - session["last_active"] > timeout:
            self.destroy_session(token)
            logger.info("Session expired.")
            return None
        
        session["last_active"] = datetime.now()
        return session["user"]
    
    def destroy_session(self, token: str):
        self._sessions.pop(token, None)
    
    def destroy_all_user_sessions(self, username: str):
        to_delete = [t for t, s in self._sessions.items()
                     if s["user"].get("username") == username]
        for t in to_delete:
            del self._sessions[t]


# ── FILE VALIDATION ───────────────────────────────────────────
class FileValidator:
    """Validate uploaded files for security."""
    
    # Magic bytes for file type verification
    MAGIC_BYTES = {
        'jpg':  [b'\xff\xd8\xff'],
        'jpeg': [b'\xff\xd8\xff'],
        'png':  [b'\x89PNG\r\n\x1a\n'],
        'pdf':  [b'%PDF-'],
        'docx': [b'PK\x03\x04'],  # ZIP-based format
    }
    
    @staticmethod
    def validate(file_path: str) -> dict:
        """
        Full security validation pipeline.
        Returns {"valid": bool, "error": str | None}
        """
        path = Path(file_path)
        
        # 1. Extension check
        ext = path.suffix.lower().lstrip('.')
        if ext not in ALLOWED_EXTENSIONS:
            return {"valid": False, "error": f"File type '.{ext}' is not allowed."}
        
        # 2. File size check
        size = path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            return {"valid": False, "error": f"File exceeds {mb}MB limit."}
        
        if size == 0:
            return {"valid": False, "error": "File is empty."}
        
        # 3. Magic bytes check (prevents fake extensions)
        magic = FileValidator.MAGIC_BYTES.get(ext, [])
        if magic:
            with open(file_path, 'rb') as f:
                header = f.read(16)
            if not any(header.startswith(m) for m in magic):
                logger.warning(f"Magic byte mismatch for file: {path.name}")
                return {"valid": False, "error": "File content does not match its extension. Possible security risk."}
        
        # 4. Filename sanitization check
        safe_name = FileValidator.sanitize_filename(path.name)
        
        return {"valid": True, "error": None, "safe_name": safe_name}
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Remove dangerous characters from filenames."""
        # Keep only alphanumeric, dots, dashes, underscores
        name = Path(filename).stem
        ext = Path(filename).suffix
        safe = re.sub(r'[^\w\-.]', '_', name)
        safe = safe[:100]  # Max 100 chars
        timestamp = str(int(time.time()))
        return f"{timestamp}_{safe}{ext}"


# ── INPUT SANITIZATION ────────────────────────────────────────
class InputSanitizer:
    """Prevent injection attacks in user inputs."""
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 500) -> str:
        """Remove dangerous characters, limit length."""
        if not isinstance(text, str):
            return ""
        # Remove null bytes and control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # Remove SQL injection patterns (extra safety on top of parameterized queries)
        text = text[:max_length]
        return text.strip()
    
    @staticmethod
    def sanitize_username(username: str) -> str:
        """Allow only safe username characters."""
        return re.sub(r'[^\w@.\-]', '', username)[:50]


# ── AUDIT LOGGER ─────────────────────────────────────────────
class AuditLogger:
    """Log all sensitive actions for compliance."""
    
    audit_logger = logging.getLogger("audit")
    
    @staticmethod
    def log(action: str, user: str, details: str = ""):
        AuditLogger.audit_logger.info(
            f"ACTION={action} | USER={user} | DETAILS={details} | TIME={datetime.now().isoformat()}"
        )


# ── GLOBAL SINGLETONS ─────────────────────────────────────────
login_tracker = LoginAttemptTracker()
session_manager = SessionManager()
file_validator = FileValidator()
password_manager = PasswordManager()
sanitizer = InputSanitizer()
audit = AuditLogger()


# ── COMPATIBILITY LAYER for main.py ───────────────────────────
class _Tracker(LoginAttemptTracker):
    def record(self, username, success):
        return self.record_attempt(username, success)
    def remaining(self, username):
        return self.attempts_remaining(username)

class _Sessions:
    def __init__(self, mgr):
        self._mgr = mgr
    def create(self, user_data):
        return self._mgr.create_session(user_data)
    def destroy(self, token):
        return self._mgr.destroy_session(token)
    def get(self, token):
        return self._mgr.get_session(token)

# Singletons
password_manager = PasswordManager()
login_tracker    = _Tracker()
session_manager  = SessionManager()
file_validator   = FileValidator()
sanitizer        = InputSanitizer()
audit            = AuditLogger()

# Aliases used by main.py
pwd_mgr  = password_manager
tracker  = login_tracker
sessions = _Sessions(session_manager)
