from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from config import settings
import hashlib
import json
import secrets
import string

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode a JWT access token"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None

def generate_device_fingerprint(user_agent: str, accept_language: str, accept_encoding: str) -> str:
    """Generate a device fingerprint from request headers"""
    fingerprint_data = {
        "user_agent": user_agent,
        "accept_language": accept_language,
        "accept_encoding": accept_encoding
    }
    fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
    return hashlib.sha256(fingerprint_string.encode()).hexdigest()

def check_suspicious_activity(ip_addresses: list, device_fingerprints: list, 
                            new_ip: str, new_fingerprint: str) -> bool:
    """Check if login attempt is suspicious"""
    # Check if we have too many different IPs
    recent_ips = set(ip_addresses[-settings.MAX_IPS_PER_MONTH:])
    if new_ip not in recent_ips and len(recent_ips) >= settings.MAX_IPS_PER_MONTH:
        return True
    
    # Check if we have too many different devices
    recent_devices = set(device_fingerprints[-settings.MAX_DEVICES_PER_ACCOUNT:])
    if new_fingerprint not in recent_devices and len(recent_devices) >= settings.MAX_DEVICES_PER_ACCOUNT:
        return True
    
    return False

def generate_verification_code(length: int = 6) -> str:
    """
    Generate a secure verification code
    Default: 6 digits
    """
    # Use only digits for easier user input
    digits = string.digits
    code = ''.join(secrets.choice(digits) for _ in range(length))
    return code

def generate_secure_token(length: int = 32) -> str:
    """
    Generate a secure random token for URLs
    Uses alphanumeric characters
    """
    alphabet = string.ascii_letters + string.digits
    token = ''.join(secrets.choice(alphabet) for _ in range(length))
    return token

def validate_verification_code(input_code: str, stored_code: str) -> bool:
    """
    Validate a verification code
    Case-insensitive comparison to handle user input variations
    """
    if not input_code or not stored_code:
        return False
    
    # Remove any spaces the user might have added
    input_code = input_code.strip().replace(' ', '')
    stored_code = stored_code.strip().replace(' ', '')
    
    # Use secrets.compare_digest for timing-attack resistant comparison
    return secrets.compare_digest(input_code.upper(), stored_code.upper())

def hash_verification_code(code: str) -> str:
    """
    Hash a verification code for secure storage
    Useful if storing codes in database instead of memory
    """
    # Add a salt to prevent rainbow table attacks
    salt = "truthlens_verification_"
    return hashlib.sha256(f"{salt}{code}".encode()).hexdigest()

def generate_password_reset_token() -> str:
    """
    Generate a secure password reset token
    """
    return generate_secure_token(48)

def is_strong_password(password: str) -> tuple[bool, Optional[str]]:
    """
    Check if password meets strength requirements
    Returns: (is_strong, error_message)
    """
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    
    if not any(c.islower() for c in password):
        return False, "La contraseña debe contener al menos una letra minúscula"
    
    if not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"
    
    # Check for common weak passwords
    weak_passwords = [
        "password", "12345678", "qwerty", "abc123", "password123",
        "admin", "letmein", "welcome", "123456789", "password1"
    ]
    
    if password.lower() in weak_passwords:
        return False, "Esta contraseña es muy común. Por favor elige una más segura"
    
    return True, None

def sanitize_email(email: str) -> str:
    """
    Sanitize email address
    """
    return email.strip().lower()

def mask_email(email: str) -> str:
    """
    Mask email for display (e.g., j***@example.com)
    """
    parts = email.split('@')
    if len(parts) != 2:
        return email
    
    local_part = parts[0]
    domain = parts[1]
    
    if len(local_part) <= 2:
        masked_local = local_part[0] + '*' * (len(local_part) - 1)
    else:
        masked_local = local_part[0] + '*' * (len(local_part) - 2) + local_part[-1]
    
    return f"{masked_local}@{domain}"

def generate_api_key() -> str:
    """
    Generate a secure API key for developer plan
    """
    prefix = "tlk_"  # TruthLens Key
    key = generate_secure_token(32)
    return f"{prefix}{key}"

def validate_api_key(api_key: str) -> bool:
    """
    Validate API key format
    """
    if not api_key:
        return False
    
    # Check prefix
    if not api_key.startswith("tlk_"):
        return False
    
    # Check length
    if len(api_key) != 36:  # tlk_ (4) + 32 characters
        return False
    
    # Check characters
    key_part = api_key[4:]
    allowed_chars = set(string.ascii_letters + string.digits)
    
    return all(c in allowed_chars for c in key_part)

# Rate limiting helpers
class RateLimiter:
    """Simple in-memory rate limiter for verification attempts"""
    
    def __init__(self):
        self.attempts = {}
    
    def check_rate_limit(self, key: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
        """
        Check if rate limit exceeded
        Returns True if within limit, False if exceeded
        """
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        
        if key not in self.attempts:
            self.attempts[key] = []
        
        # Clean old attempts
        self.attempts[key] = [
            attempt for attempt in self.attempts[key]
            if attempt > window_start
        ]
        
        # Check limit
        if len(self.attempts[key]) >= max_attempts:
            return False
        
        # Record this attempt
        self.attempts[key].append(now)
        return True
    
    def get_remaining_attempts(self, key: str, max_attempts: int = 5, window_minutes: int = 15) -> int:
        """Get number of remaining attempts"""
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        
        if key not in self.attempts:
            return max_attempts
        
        # Count recent attempts
        recent_attempts = [
            attempt for attempt in self.attempts[key]
            if attempt > window_start
        ]
        
        return max(0, max_attempts - len(recent_attempts))
    
    def reset(self, key: str):
        """Reset attempts for a key"""
        if key in self.attempts:
            del self.attempts[key]

# Global rate limiter instance
verification_rate_limiter = RateLimiter()

# Testing function
if __name__ == "__main__":
    # Test verification code generation
    print("Testing verification code generation:")
    for _ in range(5):
        code = generate_verification_code()
        print(f"Code: {code}")
    
    # Test password strength
    print("\nTesting password strength:")
    test_passwords = [
        "12345678",
        "Password1",
        "MyStr0ngP@ssw0rd",
        "weak",
        "password123"
    ]
    
    for pwd in test_passwords:
        is_strong, msg = is_strong_password(pwd)
        print(f"{pwd}: Strong={is_strong}, Message={msg}")
    
    # Test email masking
    print("\nTesting email masking:")
    test_emails = [
        "john@example.com",
        "a@test.com",
        "verylongemail@domain.com"
    ]
    
    for email in test_emails:
        masked = mask_email(email)
        print(f"{email} -> {masked}")
    
    # Test rate limiter
    print("\nTesting rate limiter:")
    limiter = RateLimiter()
    test_key = "test@example.com"
    
    for i in range(7):
        allowed = limiter.check_rate_limit(test_key, max_attempts=5)
        remaining = limiter.get_remaining_attempts(test_key, max_attempts=5)
        print(f"Attempt {i+1}: Allowed={allowed}, Remaining={remaining}")