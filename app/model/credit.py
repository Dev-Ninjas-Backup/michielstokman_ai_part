"""
app/model/credit.py
Database model for tracking daily story credits per user.

Free users get a fixed number of credits per day (default 3).
Premium users (with an active subscription) bypass credit checks entirely.
Credits auto-reset at midnight UTC.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref, relationship
from app.core.db import Base


# Default daily credits for free-tier users
FREE_TIER_DAILY_CREDITS = 3


class UserCredit(Base):
    __tablename__ = "user_credits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # How many credits remain for today
    daily_credits_remaining = Column(
        Integer, nullable=False, default=FREE_TIER_DAILY_CREDITS
    )

    # The max credits this user gets per day (can be adjusted per user if needed)
    max_daily_credits = Column(
        Integer, nullable=False, default=FREE_TIER_DAILY_CREDITS
    )

    # When the credits were last reset (used to detect midnight rollover)
    last_reset_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship — DB CASCADE; passive_deletes avoids NULL-out on user wipe
    user = relationship(
        "User",
        backref=backref("credits", cascade="all, delete-orphan", passive_deletes=True, uselist=False),
    )
