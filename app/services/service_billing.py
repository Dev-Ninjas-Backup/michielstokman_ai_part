import uuid
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.data.billing import (
    attach_payment_to_subscription,
    cancel_subscription,
    create_payment,
    create_plan,
    get_active_plans,
    get_latest_subscription_for_user,
    get_payment_by_provider_payment_id,
    get_plan_by_id,
    get_plan_by_code,
    list_payments_by_user,
    update_payment_status,
    upsert_active_subscription,
)
from app.data.user import get_user_by_id
from app.model.billing import PaymentStatus, SubscriptionInterval, SubscriptionStatus


class BillingService:
    @staticmethod
    def ensure_default_plans(db: Session) -> None:
        if not get_plan_by_code(db, "monthly_47"):
            create_plan(
                db,
                code="monthly_47",
                name="Feel More Vital - Monthly",
                description="7-day guided liberation journey recurring each month.",
                price_cents=4700,
                interval_unit=SubscriptionInterval.month,
                interval_count=1,
            )

        if not get_plan_by_code(db, "yearly_470"):
            create_plan(
                db,
                code="yearly_470",
                name="Feel More Vital - Yearly",
                description="Yearly liberation membership with discounted pricing.",
                price_cents=47000,
                interval_unit=SubscriptionInterval.year,
                interval_count=1,
            )

    @staticmethod
    def list_plans(db: Session):
        BillingService.ensure_default_plans(db)
        return get_active_plans(db)

    @staticmethod
    def start_checkout(db: Session, user_id: UUID, plan_id: UUID, provider: str):
        user = get_user_by_id(db, str(user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        plan = get_plan_by_id(db, plan_id)
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        provider_payment_id = f"pay_{uuid.uuid4().hex[:24]}"
        payment = create_payment(
            db=db,
            user_id=user_id,
            plan_id=plan.id,
            provider=provider,
            provider_payment_id=provider_payment_id,
            amount_cents=plan.price_cents,
            currency=plan.currency,
        )

        return {
            "payment_id": payment.id,
            "provider_payment_id": payment.provider_payment_id,
            "checkout_url": f"https://mockpay.local/checkout/{payment.provider_payment_id}",
            "checkout_status": payment.checkout_status,
        }

    @staticmethod
    def process_webhook(db: Session, provider_payment_id: str, event: str, failure_reason: str | None):
        payment = get_payment_by_provider_payment_id(db, provider_payment_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

        subscription_status: str | None = None

        if event == "payment_succeeded":
            payment = update_payment_status(db, payment, PaymentStatus.succeeded)
            subscription = upsert_active_subscription(
                db,
                user_id=payment.user_id,
                plan=payment.plan,
                provider_subscription_id=f"sub_{uuid.uuid4().hex[:24]}",
            )
            attach_payment_to_subscription(db, payment, subscription)
            subscription_status = subscription.status.value
        elif event == "payment_failed":
            payment = update_payment_status(db, payment, PaymentStatus.failed, failure_reason=failure_reason)
            subscription_status = SubscriptionStatus.past_due.value
        elif event == "subscription_cancelled":
            subscription = cancel_subscription(db, payment.user_id)
            if not subscription:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
            subscription_status = subscription.status.value
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported webhook event")

        return {
            "processed": True,
            "payment_status": payment.status.value,
            "subscription_status": subscription_status,
        }

    @staticmethod
    def get_subscription_status(db: Session, user_id: UUID):
        user = get_user_by_id(db, str(user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        subscription = get_latest_subscription_for_user(db, user_id)
        if not subscription:
            return {
                "user_id": user_id,
                "plan_id": None,
                "status": "none",
                "provider_subscription_id": None,
                "current_period_start": None,
                "current_period_end": None,
                "cancel_at_period_end": False,
                "cancelled_at": None,
            }

        return {
            "user_id": subscription.user_id,
            "plan_id": subscription.plan_id,
            "status": subscription.status.value,
            "provider_subscription_id": subscription.provider_subscription_id,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "cancelled_at": subscription.cancelled_at,
        }

    @staticmethod
    def cancel_user_subscription(db: Session, user_id: UUID):
        user = get_user_by_id(db, str(user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        subscription = cancel_subscription(db, user_id)
        if not subscription:
            return {"cancelled": False, "status": "none"}

        return {"cancelled": True, "status": "cancelled"}

    @staticmethod
    def payment_history(db: Session, user_id: UUID):
        user = get_user_by_id(db, str(user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        return list_payments_by_user(db, user_id)
