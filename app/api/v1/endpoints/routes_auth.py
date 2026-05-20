from fastapi import APIRouter, Depends, status, Header, HTTPException, Body, Request
from datetime import timedelta
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_token
from app.core.responses import ApiResponse, success_response
from app.schemas.user import UserCreate, UserLogin, SocialLoginRequest, Token
from app.services.service_auth import register_new_user, authenticate_user, signout_user, authenticate_social_user
from app.services.service_profile import get_current_user_profile
from app.api.deps import get_current_user
from app.model.user import User
from app.schemas.profile import UserProfileResponse
from app.utils.messages import (
    LOGIN_SUCCESSFUL,
    SIGNUP_SUCCESSFUL,
    LOGOUT_SUCCESSFUL,
    PASSWORD_RESET_SUCCESS,
    PASSWORD_UPDATE_SUCCESS,
    TOKEN_REFRESH_SUCCESSFUL,
    PROFILE_FETCHED_SUCCESS,
    FORGOT_PASSWORD_SUCCESS,
)

router = APIRouter()


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user and return a JWT token.
    Compatible with Swagger Authorize.
    """
    token_payload = register_new_user(db, user_in)
    # After creating the user, also create a default profile with null values
    from app.services.service_profile import process_profile_update
    from app.schemas.profile import UserProfileUpdate
    # Create an empty update schema (all fields optional, will be None)
    empty_update = UserProfileUpdate()
    # The new user ID is available in the token payload under 'user_id'
    user_id = token_payload.get('user_id')
    if user_id:
        # Use the same DB session to insert a placeholder profile
        process_profile_update(db, str(user_id), empty_update)

    return {
        "status": status.HTTP_201_CREATED,
        "success": True,
        "message": SIGNUP_SUCCESSFUL,
        "data": token_payload,
        "access_token": token_payload.get("access_token"),
        "token_type": "bearer"
    }


@router.post(
    "/login",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "example": "user@example.com"},
                            "password": {"type": "string", "example": "Password123!"}
                        },
                        "required": ["email", "password"]
                    }
                }
            },
            "required": True
        }
    }
)
async def login(request: Request, db: Session = Depends(get_db)):
    """
    Login with email and password. Returns a JWT access token.
    Use this token in the Authorization header as: **Bearer {token}**
    """
    email = None
    password = None

    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = await request.json()
            email = body.get("email")
            password = body.get("password")
        else:
            # Form Data (Swagger Authorize button sends username/password)
            form = await request.form()
            email = form.get("username") or form.get("email")
            password = form.get("password")
    except Exception:
        pass

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing email or password"
        )

    token_payload = authenticate_user(db, email=email, password=password)

    return {
        "status": status.HTTP_200_OK,
        "success": True,
        "message": LOGIN_SUCCESSFUL,
        "data": token_payload,
        "access_token": token_payload.get("access_token"),
        "token_type": "bearer"
    }


@router.post("/social-login", response_model=ApiResponse[Token])
def social_login(payload: SocialLoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint to securely authenticate Firebase users.
    Pass 'provider' ("firebase") and their 'id_token' from Firebase Auth.
    """
    token_payload = authenticate_social_user(db, provider=payload.provider, token=payload.token)
    return success_response(LOGIN_SUCCESSFUL, status.HTTP_200_OK, token_payload)


@router.post("/signout", response_model=ApiResponse[None])
def signout(authorization: str = Header(...), db: Session = Depends(get_db)):
    """
    Sign out the current user by invalidating their token.
    Pass the token in the Authorization header as: Bearer <token>
    """
    try:
        # Extract token from "Bearer <token>"
        token = authorization.split(" ")[1]
    except IndexError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = verify_token(token, db)
    result = signout_user(db, user_id)
    return success_response(LOGOUT_SUCCESSFUL, status.HTTP_200_OK)


@router.get("/auth/profile", response_model=ApiResponse[UserProfileResponse])
def get_auth_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Alias for /me/profile used by the frontend.
    """
    profile = get_current_user_profile(db, user_id=str(current_user.id))
    return success_response(PROFILE_FETCHED_SUCCESS, status.HTTP_200_OK, profile)


@router.post("/auth/refresh")
def refresh_token(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Returns a fresh JWT access token for the currently authenticated user.
    """
    from app.core.config import settings
    from app.core.security import create_access_token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(current_user.id)},
        user_token_version=current_user.token_version,
        expires_delta=access_token_expires,
    )
    return {
        "status": status.HTTP_200_OK,
        "success": True,
        "message": TOKEN_REFRESH_SUCCESSFUL,
        "data": {"access_token": access_token, "token_type": "bearer"},
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/auth/forgot-password")
def forgot_password():
    return success_response(FORGOT_PASSWORD_SUCCESS, status.HTTP_200_OK)


@router.post("/auth/reset-password")
def reset_password():
    return success_response(PASSWORD_RESET_SUCCESS, status.HTTP_200_OK)


@router.post("/auth/update-password")
def update_password():
    return success_response(PASSWORD_UPDATE_SUCCESS, status.HTTP_200_OK)
