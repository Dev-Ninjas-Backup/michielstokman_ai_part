import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ContentType(str, enum.Enum):
    confession = "confession"
    meditation = "meditation"
    journey = "journey"


class StoryStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SubmissionStatus(str, enum.Enum):
    pending = "pending"
    reviewed = "reviewed"
    accepted = "accepted"
    rejected = "rejected"


class EnrollmentStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class DayStatus(str, enum.Enum):
    locked = "locked"
    ready = "ready"
    completed = "completed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    credit_wallet: Mapped["CreditWallet"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)

    true_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    education: Mapped[str | None] = mapped_column(String(120), nullable=True)
    annual_income: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sexual_orientation: Mapped[str | None] = mapped_column(String(120), nullable=True)

    life_phase: Mapped[str | None] = mapped_column(String(120), nullable=True)

    slider_desire_relationship: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_life_purpose: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_career_money: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_true_self: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_security_energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_free_freedom: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_health_body: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_enlightenment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slider_social_relational: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[User] = relationship(back_populates="profile")


class CreditWallet(Base):
    __tablename__ = "credit_wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=3)
    remaining: Mapped[int] = mapped_column(Integer, default=3)
    last_reset_date: Mapped[date] = mapped_column(Date, default=date.today)

    user: Mapped[User] = relationship(back_populates="credit_wallet")


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), index=True)
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[float] = mapped_column(Float, default=4.2)
    duration_sec: Mapped[int] = mapped_column(Integer, default=720)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType))
    track_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_context: Mapped[dict] = mapped_column(JSON, default=dict)
    story_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[StoryStatus] = mapped_column(Enum(StoryStatus), default=StoryStatus.processing)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StoryReflection(Base):
    __tablename__ = "story_reflections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    resonance_score: Mapped[float] = mapped_column(Float)
    moment_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    thought_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reaction: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType))
    title: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    growth_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    life_phase_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    contains_sensitive_content: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus), default=SubmissionStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class LiberationPlan(Base):
    __tablename__ = "liberation_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer, default=4700)
    days_count: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LiberationEnrollment(Base):
    __tablename__ = "liberation_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("liberation_plans.id"), index=True)
    status: Mapped[EnrollmentStatus] = mapped_column(Enum(EnrollmentStatus), default=EnrollmentStatus.active)
    payment_status: Mapped[str] = mapped_column(String(30), default="pending")
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LiberationDayProgress(Base):
    __tablename__ = "liberation_day_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    enrollment_id: Mapped[str] = mapped_column(String(36), ForeignKey("liberation_enrollments.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[DayStatus] = mapped_column(Enum(DayStatus), default=DayStatus.locked)
    energy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reflection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    carry_forward: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("enrollment_id", "day_number", name="uq_enrollment_day"),)
