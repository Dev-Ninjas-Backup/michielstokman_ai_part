from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.schema_billing import (
    PaymentHistoryItem,
    PaymentWebhookRequest,
    PaymentWebhookResponse,
    StartCheckoutRequest,
    StartCheckoutResponse,
)
from app.services.service_billing import BillingService

router = APIRouter()


@router.post("/payment/checkout/start", response_model=StartCheckoutResponse)
def start_checkout(payload: StartCheckoutRequest, db: Session = Depends(get_db)):
    return BillingService.start_checkout(
        db=db,
        user_id=payload.user_id,
        plan_id=payload.plan_id,
        provider=payload.provider,
    )


@router.post("/payment/webhook", response_model=PaymentWebhookResponse)
def payment_webhook(payload: PaymentWebhookRequest, db: Session = Depends(get_db)):
    return BillingService.process_webhook(
        db=db,
        provider_payment_id=payload.provider_payment_id,
        event=payload.event,
        failure_reason=payload.failure_reason,
    )


@router.get("/payment/history/{user_id}", response_model=list[PaymentHistoryItem])
def payment_history(user_id: UUID, db: Session = Depends(get_db)):
    return BillingService.payment_history(db=db, user_id=user_id)
