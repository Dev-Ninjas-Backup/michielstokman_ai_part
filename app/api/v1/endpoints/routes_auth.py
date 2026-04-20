from fastapi import APIRouter, Depends, status, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_token
from app.schemas.user import UserCreate, Token, UserLogin, SocialLoginRequest
from app.schemas.schema_system import MessageResponse
from app.services.service_auth import register_new_user, authenticate_user, signout_user, authenticate_social_user

router = APIRouter()

@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with email and password and return a JWT token.
    """
    return register_new_user(db, user_in)


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """
    Login endpoint to get an access token for future requests.
    Expects a standard JSON body with 'email' and 'password'.
    """
    return authenticate_user(db, email=user_in.email, password=user_in.password)


@router.post("/social-login", response_model=Token)
def social_login(payload: SocialLoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint to securely authenticate Google/Apple users.
    Pass 'provider' ("google" or "apple") and their 'token'.
    """
    return authenticate_social_user(db, provider=payload.provider, token=payload.token)


@router.post("/signout", response_model=MessageResponse)
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
            detail="Invalid authorization header format"
        )
    
    user_id = verify_token(token, db)
    return signout_user(db, user_id)

