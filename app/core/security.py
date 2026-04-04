from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt

from app.core.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if the provided plain password matches the hashed version."""
    try:
        return bcrypt.checkpw(
            password=plain_password.encode('utf-8'),
            hashed_password=hashed_password.encode('utf-8')
        )
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash for a plain password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a JWT access token encoding the provided data (e.g., user email or id)."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode.update({"exp": expire})
    
    # We use the config variables you just added to .env
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
