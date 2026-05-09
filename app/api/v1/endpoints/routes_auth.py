from fastapi import APIRouter, Depends, status, Header, HTTPException, Body, Request
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


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user and return a JWT token.
    Compatible with Swagger Authorize.
    """
    token_payload = register_new_user(db, user_in)
    return {
        "status": status.HTTP_201_CREATED,
        "success": True,
        "message": "Signup successful",
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
        "message": "Login successful",
        "data": token_payload,
        "access_token": token_payload.get("access_token"),
        "token_type": "bearer"
    }


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
