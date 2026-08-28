from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.schemas.schema_billing import (
    CancelSubscriptionRequest,
    CancelSubscriptionResponse,
    SubscriptionPlanResponse,
    SubscriptionStatusResponse,
)
from app.services.service_billing import BillingService

router = APIRouter()


@router.get("/subscription/plans", response_model=ApiResponse[list[SubscriptionPlanResponse]])
def subscription_plans(db: Session = Depends(get_db)):
    plans = BillingService.list_plans(db)
    return success_response("Subscription plans fetched successfully", status.HTTP_200_OK, plans)


@router.get("/subscription/status", response_model=ApiResponse[SubscriptionStatusResponse])
def get_subscription_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current authenticated user's subscription status."""
    subscription = BillingService.get_subscription_status(db=db, user_id=current_user.id)
    return success_response("Subscription status fetched successfully", status.HTTP_200_OK, subscription)


@router.post("/subscription/cancel", response_model=ApiResponse[CancelSubscriptionResponse])
def cancel_subscription(
    payload: CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = BillingService.cancel_user_subscription(db=db, user_id=current_user.id)
    return success_response("Subscription cancellation processed", status.HTTP_200_OK, result)
