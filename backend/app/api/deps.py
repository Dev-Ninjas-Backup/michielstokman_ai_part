from datetime import date

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import CreditWallet, User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return user


def get_or_create_wallet(db: Session, user_id: str) -> CreditWallet:
    wallet = db.query(CreditWallet).filter(CreditWallet.user_id == user_id).first()
    if not wallet:
        wallet = CreditWallet(user_id=user_id, daily_limit=3, remaining=3, last_reset_date=date.today())
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


def reset_wallet_if_needed(db: Session, wallet: CreditWallet) -> CreditWallet:
    today = date.today()
    if wallet.last_reset_date != today:
        wallet.last_reset_date = today
        wallet.remaining = wallet.daily_limit
        db.commit()
        db.refresh(wallet)
    return wallet
