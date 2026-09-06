from datetime import datetime, timedelta, timezone
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.data.user import get_user_by_id
from app.model.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/v1/login")

TOKEN_INVALIDATED_DETAIL = "Token has been invalidated. Please login again."


def _assert_token_version(payload: dict, user: User) -> None:
    """Reject JWTs whose version no longer matches User.token_version (sign-out)."""
    if user.token_version != payload.get("version"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=TOKEN_INVALIDATED_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )


def refresh_access_token(db: Session, token: str) -> str:
    """
    Issue a new access token from an existing JWT.

    Signature and token_version are required. Expiry is allowed within a 7-day
    grace window so the frontend can rotate a near-expired or just-expired token
    without a separate refresh-token family.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    exp = payload.get("exp")
    if exp is not None:
        expired_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        if datetime.now(timezone.utc) - expired_at > timedelta(days=7):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is too old to refresh. Please login again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if payload.get("is_guest"):
        return create_access_token(
            data={"sub": str(user_id), "is_guest": True},
            user_token_version=0,
            expires_delta=timedelta(minutes=settings.GUEST_TOKEN_EXPIRE_MINUTES),
        )

    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    _assert_token_version(payload, user)
    return create_access_token(
        data={"sub": str(user.id)},
        user_token_version=user.token_version,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


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
        if payload.get("is_guest"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This feature requires a registered account. Please sign up or log in.",
            )
    except HTTPException:
        raise
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
    _assert_token_version(payload, user)
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
        if payload.get("is_guest"):
            return None
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
    _assert_token_version(payload, user)
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


# ---------------------------------------------------------------------------
# Guest-aware authentication helpers
# ---------------------------------------------------------------------------

def get_current_user_or_guest(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Decode the JWT and return a dict with either a real user or guest context.

    Returns
    -------
    dict with keys:
        user     – User instance or None
        is_guest – bool
        guest_id – str (UUID) if guest, else None
    """
    authorization: str = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
        token = parts[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    # Guest tokens carry an `is_guest` claim
    if payload.get("is_guest"):
        guest_id = payload.get("sub")
        if not guest_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid guest token")
        return {"user": None, "is_guest": True, "guest_id": guest_id}

    # Otherwise it's a normal user token
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    _assert_token_version(payload, user)
    return {"user": user, "is_guest": False, "guest_id": None}


def require_registered_user(
    auth_ctx: dict = Depends(get_current_user_or_guest),
) -> User:
    """Dependency that ensures the caller is a registered (non-guest) user."""
    if auth_ctx["is_guest"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a registered account. Please sign up or log in.",
        )
    return auth_ctx["user"]


def enforce_guest_story_limit(
    story_id: str,
    db: Session = Depends(get_db),
    auth_ctx: dict = Depends(get_current_user_or_guest),
):
    """
    For guests: checks whether they have already read a story today.
    If yes, raises 429. If no, allows through and returns the guest_id so
    the route can record the access.

    For registered users: passes through with no restrictions.

    Returns
    -------
    dict with keys: user, is_guest, guest_id (same as auth_ctx, enriched)
    """
    if not auth_ctx["is_guest"]:
        return auth_ctx  # registered users are unrestricted

    from datetime import date
    from app.model.guest_session import GuestSession

    guest_id = auth_ctx["guest_id"]
    session = db.query(GuestSession).filter_by(id=guest_id).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid guest session. Please call /v1/guest-login first.",
        )

    today = date.today()
    # Allow guest to re-access the same story they unlocked today without blocking them
    if session.last_story_date == today and session.last_story_id != story_id:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Guest limit reached — you can read one story per day. Sign up for unlimited access!",
        )

    return auth_ctx


