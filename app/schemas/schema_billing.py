from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, UUID4


class SubscriptionPlanResponse(BaseModel):
    id: UUID4
    code: str
    name: str
    description: str | None = None
    price_cents: int
    currency: str
    interval_unit: Literal["month", "year"]
    interval_count: int

    model_config = ConfigDict(from_attributes=True)


class StartCheckoutRequest(BaseModel):
    user_id: UUID4
    plan_id: UUID4
    provider: str = "mockpay"


class StartCheckoutResponse(BaseModel):
    payment_id: UUID4
    provider_payment_id: str
    checkout_url: str
    checkout_status: str


class PaymentWebhookRequest(BaseModel):
    provider_payment_id: str
    event: Literal["payment_succeeded", "payment_failed", "subscription_cancelled"]
    failure_reason: str | None = None


class PaymentWebhookResponse(BaseModel):
    processed: bool
    payment_status: Literal["pending", "succeeded", "failed", "refunded"]
    subscription_status: Literal["active", "past_due", "cancelled", "expired"] | None = None


class PaymentHistoryItem(BaseModel):
    id: UUID4
    user_id: UUID4
    plan_id: UUID4
    subscription_id: UUID4 | None = None
    provider: str
    provider_payment_id: str
    amount_cents: int
    currency: str
    status: Literal["pending", "succeeded", "failed", "refunded"]
    checkout_status: str
    failure_reason: str | None = None
    created_at: datetime
    paid_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionStatusResponse(BaseModel):
    user_id: UUID4
    plan_id: UUID4 | None = None
    status: Literal["active", "past_due", "cancelled", "expired", "none"]
    provider_subscription_id: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    cancelled_at: datetime | None = None


class CancelSubscriptionRequest(BaseModel):
    user_id: UUID4


class CancelSubscriptionResponse(BaseModel):
    cancelled: bool
    status: Literal["cancelled", "none"]
