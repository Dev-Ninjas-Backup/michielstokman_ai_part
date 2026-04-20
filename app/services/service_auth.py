from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token
from app.schemas.user import UserCreate
from app.data.user import (
    get_user_by_email, create_user, update_last_login, 
    get_user_by_id, increment_token_version, get_user_by_oauth, link_oauth_account
)

def register_new_user(db: Session, user_in: UserCreate):
    """
    Business logic to validate, register, and auto-login a new standard user.
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

    # Mirror login/social-login behavior so frontend can immediately call
    # protected profile endpoints after signup.
    update_last_login(db, new_user)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(new_user.id)},
        user_token_version=new_user.token_version,
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user,
        "is_new_user": True,
    }


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
        "user": user,
        "is_new_user": False,
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

def authenticate_social_user(db: Session, provider: str, token: str):
    """
    Business logic to verify a social login token, create/link the user, and generate a JWT session token.
    """
    email = None
    provider_account_id = None
    
    if provider.lower() == "google":
        if not settings.GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google Auth not configured")
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            
            user_info = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
            email = user_info.get('email')
            provider_account_id = user_info['sub']
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google Token")
            
    elif provider.lower() == "apple":
        if not settings.APPLE_CLIENT_ID:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Apple Auth not configured")
        try:
            import jwt 
            import requests
            from jwt.algorithms import RSAAlgorithm
            
            # Extract header securely to get Apple's Key ID (kid)
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise ValueError("No kid found in Apple token header")
                
            # Fetch Apple's public signature keys
            jwks_response = requests.get("https://appleid.apple.com/auth/keys", timeout=5)
            jwks_response.raise_for_status()
            apple_keys = jwks_response.json().get("keys", [])
            
            # Find the matching RSA key used to sign this token
            matched_key = next((key for key in apple_keys if key.get("kid") == kid), None)
            if not matched_key:
                raise ValueError("Apple public key mismatch")
                
            # Convert JSON Web Key to a standard RSA Public Key
            public_key = RSAAlgorithm.from_jwk(matched_key)
            
            # Fully and securely verify the token's cryptographic signature
            verified_payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=settings.APPLE_CLIENT_ID,
                issuer="https://appleid.apple.com"
            )
            
            email = verified_payload.get("email")
            provider_account_id = verified_payload.get("sub")
            if not provider_account_id:
                raise ValueError("No subscriber ID found")
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Apple Token")
            
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider")
        
    if not email or not provider_account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not extract necessary user info from token")

    # Find the user by their OAuth account
    is_new_user = False
    user = get_user_by_oauth(db, provider.lower(), provider_account_id)
    
    if not user:
        # Fallback: check if the user signed up via email normally or via another provider
        user = get_user_by_email(db, email=email)
        if not user:
            # Make a completely new account (no password)
            user = create_user(db, email=email, password_hash=None)
            user.is_verified = True # Social accounts are considered verified
            is_new_user = True
            
        # Link this new oauth provider to the user's account
        link_oauth_account(db, str(user.id), provider.lower(), provider_account_id)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account")
        
    update_last_login(db, user)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        user_token_version=user.token_version,
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
        "is_new_user": is_new_user,
    }
