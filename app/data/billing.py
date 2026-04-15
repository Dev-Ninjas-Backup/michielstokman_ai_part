from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.billing import (
    PaymentStatus,
    PaymentTransaction,
    SubscriptionInterval,
    SubscriptionPlan,
    SubscriptionStatus,
    UserSubscription,
)


def get_active_plans(db: Session) -> list[SubscriptionPlan]:
    return db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active.is_(True)).all()


def get_plan_by_id(db: Session, plan_id: UUID) -> SubscriptionPlan | None:
    return db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()


def get_plan_by_code(db: Session, code: str) -> SubscriptionPlan | None:
    return db.query(SubscriptionPlan).filter(SubscriptionPlan.code == code).first()


def create_plan(
    db: Session,
    code: str,
    name: str,
    description: str,
    price_cents: int,
    interval_unit: SubscriptionInterval,
    interval_count: int = 1,
    currency: str = "EUR",
) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        code=code,
        name=name,
        description=description,
        price_cents=price_cents,
        interval_unit=interval_unit,
        interval_count=interval_count,
        currency=currency,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def create_payment(
    db: Session,
    user_id: UUID,
    plan_id: UUID,
    provider: str,
    provider_payment_id: str,
    amount_cents: int,
    currency: str,
) -> PaymentTransaction:
    payment = PaymentTransaction(
        user_id=user_id,
        plan_id=plan_id,
        provider=provider,
        provider_payment_id=provider_payment_id,
        amount_cents=amount_cents,
        currency=currency,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def get_payment_by_provider_payment_id(db: Session, provider_payment_id: str) -> PaymentTransaction | None:
    return (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.provider_payment_id == provider_payment_id)
        .first()
    )


def update_payment_status(
    db: Session,
    payment: PaymentTransaction,
    status: PaymentStatus,
    failure_reason: str | None = None,
) -> PaymentTransaction:
    setattr(payment, "status", status)
    setattr(payment, "failure_reason", failure_reason)
    if status == PaymentStatus.succeeded:
        setattr(payment, "paid_at", datetime.now(timezone.utc))
        setattr(payment, "checkout_status", "completed")
    elif status == PaymentStatus.failed:
        setattr(payment, "checkout_status", "failed")

    db.commit()
    db.refresh(payment)
    return payment

def count_active_subscriptions(db: Session) -> int:
    """Get count of all active subscriptions."""
    return db.query(UserSubscription).filter(
        UserSubscription.status == SubscriptionStatus.active
    ).count()

def get_total_revenue_today(db: Session) -> int:
    """Get total revenue (in cents) from successful payments today."""
    from sqlalchemy import func
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = db.query(func.sum(PaymentTransaction.amount_cents)).filter(
        PaymentTransaction.status == PaymentStatus.succeeded,
        PaymentTransaction.paid_at >= today_start
    ).scalar()
    return result or 0

def count_failed_payments_today(db: Session) -> int:
    """Get count of failed payments today."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(PaymentTransaction).filter(
        PaymentTransaction.status == PaymentStatus.failed,
        PaymentTransaction.created_at >= today_start
    ).count()
    return payment


def get_latest_subscription_for_user(db: Session, user_id: UUID) -> UserSubscription | None:
    return (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user_id)
        .order_by(UserSubscription.created_at.desc())
        .first()
    )


def upsert_active_subscription(
    db: Session,
    user_id: UUID,
    plan: SubscriptionPlan,
    provider_subscription_id: str,
) -> UserSubscription:
    subscription = get_latest_subscription_for_user(db, user_id)

    now = datetime.now(timezone.utc)
    interval_unit = getattr(plan, "interval_unit")
    interval_count = int(getattr(plan, "interval_count"))
    if interval_unit == SubscriptionInterval.year:
        period_end = now + timedelta(days=365 * interval_count)
    else:
        period_end = now + timedelta(days=30 * interval_count)

    if subscription:
        setattr(subscription, "plan_id", plan.id)
        setattr(subscription, "status", SubscriptionStatus.active)
        setattr(subscription, "provider_subscription_id", provider_subscription_id)
        setattr(subscription, "current_period_start", now)
        setattr(subscription, "current_period_end", period_end)
        setattr(subscription, "cancel_at_period_end", False)
        setattr(subscription, "cancelled_at", None)
    else:
        subscription = UserSubscription(
            user_id=user_id,
            plan_id=plan.id,
            status=SubscriptionStatus.active,
            provider_subscription_id=provider_subscription_id,
            current_period_start=now,
            current_period_end=period_end,
            cancel_at_period_end=False,
        )
        db.add(subscription)

    db.commit()
    db.refresh(subscription)
    return subscription


def attach_payment_to_subscription(
    db: Session,
    payment: PaymentTransaction,
    subscription: UserSubscription,
) -> PaymentTransaction:
    payment.subscription_id = subscription.id
    db.commit()
    db.refresh(payment)
    return payment


def cancel_subscription(db: Session, user_id: UUID) -> UserSubscription | None:
    subscription = get_latest_subscription_for_user(db, user_id)
    if not subscription:
        return None

    setattr(subscription, "status", SubscriptionStatus.cancelled)
    setattr(subscription, "cancel_at_period_end", False)
    setattr(subscription, "cancelled_at", datetime.now(timezone.utc))
    db.commit()
    db.refresh(subscription)
    return subscription


def list_payments_by_user(db: Session, user_id: UUID) -> list[PaymentTransaction]:
    return (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.user_id == user_id)
        .order_by(PaymentTransaction.created_at.desc())
        .all()
    )
