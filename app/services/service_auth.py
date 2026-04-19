from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token
from app.schemas.user import UserCreate
from app.data.user import get_user_by_email, create_user, update_last_login, get_user_by_id, increment_token_version

def register_new_user(db: Session, user_in: UserCreate):
    """
    Business logic to validate and register a new standard user.
    """
    user = get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )
    
    # Securely hash the plain text password before storing it
    hashed_password = get_password_hash(user_in.password)
    new_user = create_user(db, email=user_in.email, password_hash=hashed_password)
    
    return new_user


def authenticate_user(db: Session, email: str, password: str):
    """
    Business logic to verify credentials and generate a JWT session token.
    """
    user = get_user_by_email(db, email=email)
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify the password against the stored bcrypt hash
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Ensure they haven't been banned or deactivated
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    # Track when the user last logged in
    update_last_login(db, user)

    # Generate the JWT Token identifying the user ID securely
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        user_token_version=user.token_version,
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

def signout_user(db: Session, user_id: str):
    """
    Invalidate all active tokens by incrementing the user's token_version.
    The user must provide a valid token to call this.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    increment_token_version(db, user)
    return {"message": "Successfully signed out"}
