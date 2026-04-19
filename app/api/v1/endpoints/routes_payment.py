from uuid import UUID

from fastapi import APIRouter, Depends, Request, Header
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


@router.post("/payment/webhook") # Note: no response_model set because it returns varying dicts now
async def payment_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db)
):
    payload = await request.body()
    return BillingService.process_webhook(
        db=db,
        payload=payload,
        sig_header=stripe_signature,
    )


@router.get("/payment/history/{user_id}", response_model=list[PaymentHistoryItem])
def payment_history(user_id: UUID, db: Session = Depends(get_db)):
    return BillingService.payment_history(db=db, user_id=user_id)
