from uuid import UUID

from fastapi import APIRouter, Depends, Request, Header, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.schema_billing import (
    StartCheckoutRequest,
    StartCheckoutResponse,
    PaymentWebhookResponse,
    PaymentHistoryItem,
)
from app.services.service_billing import BillingService

router = APIRouter()


@router.post("/payment/checkout/start", response_model=ApiResponse[StartCheckoutResponse])
def start_checkout(payload: StartCheckoutRequest, db: Session = Depends(get_db)):
    checkout = BillingService.start_checkout(
        db=db,
        user_id=payload.user_id,
        plan_id=payload.plan_id,
        journey_id=payload.journey_id,
        journey_code=payload.journey_code,
        provider=payload.provider,
    )
    return success_response("Checkout started successfully", status.HTTP_200_OK, checkout)


@router.post("/payment/webhook", response_model=ApiResponse[PaymentWebhookResponse])
async def payment_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db)
):
    payload = await request.body()
    result = BillingService.process_webhook(
        db=db,
        payload=payload,
        sig_header=stripe_signature,
    )
    message = "Webhook processed successfully" if result.get("processed") else "Webhook not processed"
    return success_response(message, status.HTTP_200_OK, result)


@router.get("/payment/history/{user_id}", response_model=ApiResponse[list[PaymentHistoryItem]])
def payment_history(user_id: UUID, db: Session = Depends(get_db)):
    history = BillingService.payment_history(db=db, user_id=user_id)
    return success_response("Payment history fetched successfully", status.HTTP_200_OK, history)
