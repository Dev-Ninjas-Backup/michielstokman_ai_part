from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.user import UserCreate, UserResponse, Token, UserLogin
from app.services.service_auth import register_new_user, authenticate_user

router = APIRouter()

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with email and password.
    """
    return register_new_user(db, user_in)


@router.post("/login", response_model=Token)
def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible token login, getting an access token for future requests.
    Note: OAuth2Form expects the email to be passed in the 'username' field.
    """
    return authenticate_user(db, email=form_data.username, password=form_data.password)
