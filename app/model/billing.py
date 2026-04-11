import enum
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class SubscriptionInterval(str, enum.Enum):
    month = "month"
    year = "year"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"
    expired = "expired"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price_cents = Column(Integer, nullable=False)
    currency = Column(String, default="EUR", nullable=False)
    interval_unit = Column(Enum(SubscriptionInterval), nullable=False)
    interval_count = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    subscriptions = relationship("UserSubscription", back_populates="plan")
    payments = relationship("PaymentTransaction", back_populates="plan")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), index=True, nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.active, nullable=False)
    provider_customer_id = Column(String, nullable=True)
    provider_subscription_id = Column(String, nullable=True)
    current_period_start = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    current_period_end = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=30),
        nullable=False,
    )
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    payments = relationship("PaymentTransaction", back_populates="subscription")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), index=True, nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id"), index=True, nullable=True)
    provider = Column(String, default="mockpay", nullable=False)
    provider_payment_id = Column(String, unique=True, index=True, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, default="EUR", nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    checkout_status = Column(String, default="created", nullable=False)
    failure_reason = Column(String, nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    paid_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")
    plan = relationship("SubscriptionPlan", back_populates="payments")
    subscription = relationship("UserSubscription", back_populates="payments")
