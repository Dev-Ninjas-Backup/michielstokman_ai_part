"""
app/data/credit.py
Database operations for the user credit system.

Handles auto-reset at midnight UTC, credit checking, and deduction.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.model.credit import UserCredit, FREE_TIER_DAILY_CREDITS
from app.model.billing import UserSubscription, SubscriptionStatus


def _today_midnight_utc() -> datetime:
    """Returns midnight UTC of the current day."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_or_create_credit(db: Session, user_id: str) -> UserCredit:
    """
    Get the user's credit record.
    If it doesn't exist yet (new user), create one with full daily credits.
    If the last reset was before today's midnight, auto-reset the credits.
    """
    credit = (
        db.query(UserCredit)
        .filter(UserCredit.user_id == user_id)
        .first()
    )

    if not credit:
        credit = UserCredit(
            user_id=user_id,
            daily_credits_remaining=FREE_TIER_DAILY_CREDITS,
            max_daily_credits=FREE_TIER_DAILY_CREDITS,
            last_reset_at=datetime.now(timezone.utc),
        )
        db.add(credit)
        db.commit()
        db.refresh(credit)
        return credit

    # Auto-reset if last reset was before today's midnight
    midnight = _today_midnight_utc()
    if credit.last_reset_at < midnight:
        credit.daily_credits_remaining = credit.max_daily_credits
        credit.last_reset_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(credit)

    return credit


def is_premium_user(db: Session, user_id: str) -> bool:
    """
    Check if the user has any active subscription.
    Premium users bypass all credit checks.
    """
    active_sub = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_id,
            UserSubscription.status == SubscriptionStatus.active,
        )
        .first()
    )
    return active_sub is not None


def has_credits(db: Session, user_id: str) -> bool:
    """
    Returns True if the user can generate a story right now.
    Premium users always return True.
    Free users return True only if they have remaining daily credits.
    """
    if is_premium_user(db, user_id):
        return True

    credit = get_or_create_credit(db, user_id)
    return credit.daily_credits_remaining > 0


def deduct_credit(db: Session, user_id: str) -> int:
    """
    Deducts 1 credit from the user's daily allowance.
    Returns the number of credits remaining after deduction.
    Premium users are not deducted (returns -1 to indicate unlimited).
    """
    if is_premium_user(db, user_id):
        return -1  # unlimited

    credit = get_or_create_credit(db, user_id)

    if credit.daily_credits_remaining <= 0:
        return 0

    credit.daily_credits_remaining -= 1
    db.commit()
    db.refresh(credit)
    return credit.daily_credits_remaining
