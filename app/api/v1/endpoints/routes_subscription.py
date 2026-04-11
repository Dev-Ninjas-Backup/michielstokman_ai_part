from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.schema_billing import (
    CancelSubscriptionRequest,
    CancelSubscriptionResponse,
    SubscriptionPlanResponse,
    SubscriptionStatusResponse,
)
from app.services.service_billing import BillingService

router = APIRouter()


@router.get("/subscription/plans", response_model=list[SubscriptionPlanResponse])
def subscription_plans(db: Session = Depends(get_db)):
    return BillingService.list_plans(db)


@router.get("/subscription/{user_id}", response_model=SubscriptionStatusResponse)
def get_subscription_status(user_id: UUID, db: Session = Depends(get_db)):
    return BillingService.get_subscription_status(db=db, user_id=user_id)


@router.post("/subscription/cancel", response_model=CancelSubscriptionResponse)
def cancel_subscription(payload: CancelSubscriptionRequest, db: Session = Depends(get_db)):
    return BillingService.cancel_user_subscription(db=db, user_id=payload.user_id)
