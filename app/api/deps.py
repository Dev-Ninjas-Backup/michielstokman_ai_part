from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.data.user import get_user_by_id
from app.model.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/v1/login")

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    authorization: str = request.headers.get("Authorization")
    if not authorization:
        return None
    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        token = parts[1]
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user



def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user


def check_story_credit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency that checks if the user has credits to generate a story.
    - Premium users (active subscription) → always allowed.
    - Free users → must have daily_credits_remaining > 0.
    Raises 402 Payment Required if the user is out of credits.
    Does NOT deduct — deduction happens after successful generation.
    """
    from app.data.credit import has_credits

    if not has_credits(db, str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Daily credit limit reached. Upgrade to Premium for unlimited stories.",
        )
    return current_user

