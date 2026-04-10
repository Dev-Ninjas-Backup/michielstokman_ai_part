from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_or_create_wallet, reset_wallet_if_needed
from app.core.database import get_db
from app.models.entities import User
from app.schemas.dto import ConsumeCreditRequest, ConsumeCreditResponse, CreditWalletResponse


router = APIRouter(prefix="/me/credits", tags=["Credits"])


@router.get("", response_model=CreditWalletResponse)
def get_credits(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    wallet = reset_wallet_if_needed(db, get_or_create_wallet(db, current_user.id))
    return CreditWalletResponse.model_validate(wallet, from_attributes=True)


@router.post("/consume", response_model=ConsumeCreditResponse)
def consume_credit(
    _payload: ConsumeCreditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = reset_wallet_if_needed(db, get_or_create_wallet(db, current_user.id))
    if wallet.remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="NO_CREDITS",
        )
    wallet.remaining -= 1
    db.commit()
    return ConsumeCreditResponse(consumed=True, remaining=wallet.remaining)
