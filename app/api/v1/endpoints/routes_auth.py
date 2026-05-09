from typing import Optional
from fastapi import APIRouter, Depends, status, Header, HTTPException, Body
from fastapi.security import OAuth2PasswordRequestForm
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

router = APIRouter()


@router.post("/signup", response_model=ApiResponse[Token], status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with email and password and return a JWT token.
    """
    token_payload = register_new_user(db, user_in)
    return success_response("Signup successful", status.HTTP_201_CREATED, token_payload)


@router.post("/login", response_model=ApiResponse[Token])
def login(
    user_in: Optional[UserLogin] = Body(None),
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Login endpoint to get an access token for future requests.
    Supports both standard JSON body and OAuth2 Form Data (Swagger Authorize).
    """
    # Use JSON if provided, otherwise fallback to form data (username is email)
    email = user_in.email if user_in else form_data.username
    password = user_in.password if user_in else form_data.password

    token_payload = authenticate_user(db, email=email, password=password)
    return success_response("Login successful", status.HTTP_200_OK, token_payload)


@router.post("/social-login", response_model=ApiResponse[Token])
def social_login(payload: SocialLoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint to securely authenticate Google/Apple users.
    Pass 'provider' ("google" or "apple") and their 'token'.
    """
    token_payload = authenticate_social_user(db, provider=payload.provider, token=payload.token)
    return success_response("Login successful", status.HTTP_200_OK, token_payload)


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
    return success_response(result.get("message", "Successfully signed out"), status.HTTP_200_OK)


@router.get("/auth/profile", response_model=ApiResponse[UserProfileResponse])
def get_auth_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Alias for /me/profile used by the frontend.
    """
    profile = get_current_user_profile(db, user_id=str(current_user.id))
    return success_response("Profile fetched successfully", status.HTTP_200_OK, profile)


@router.post("/auth/refresh", response_model=ApiResponse[Token])
def refresh_token(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Placeholder for token refresh logic. For now, just returns a new token for the same user.
    """
    # In a real app, this would verify a refresh token and issue a new access token.
    # For now, we mock it to prevent frontend errors.
    from app.services.service_auth import create_user_token
    token_payload = create_user_token(current_user)
    return success_response("Token refreshed successfully", status.HTTP_200_OK, token_payload)


@router.post("/auth/forgot-password")
def forgot_password():
    return success_response("If email exists, reset link sent", status.HTTP_200_OK)


@router.post("/auth/reset-password")
def reset_password():
    return success_response("Password reset successful", status.HTTP_200_OK)


@router.post("/auth/update-password")
def update_password():
    return success_response("Password updated successfully", status.HTTP_200_OK)
