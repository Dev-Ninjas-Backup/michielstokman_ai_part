"""
app/model/liberation.py

Database models for the Liberation Journey product catalog and user progress.

Two layers:
  1. CATALOG  – LiberationDefinition + LiberationDayDefinition
     Describes every journey that is offered on the site (created by
     admins or submitted by premium users for review).
  2. PROGRESS – UserJourney + UserJourneyStep
     Tracks a single user's enrolment and day-by-day progress.
"""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, String, Integer, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


# ── Enums ───────────────────────────────────────────────────────────────────

class DefinitionStatus(str, enum.Enum):
    """Review status for user-submitted liberation definitions."""
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class JourneyStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class StepStatus(str, enum.Enum):
    locked = "locked"
    available = "available"
    completed = "completed"


# ── Legacy fallback themes (kept for backwards compatibility) ───────────────
JOURNEY_DAY_THEMES = {
    1: "Awakening",
    2: "Softening",
    3: "Releasing",
    4: "Grounding",
    5: "Flowing",
    6: "Radiating",
    7: "Full Bloom",
}


# ============================================================================
# CATALOG LAYER — the "product" blueprint that lives on the storefront
# ============================================================================

class LiberationDefinition(Base):
    """
    A single liberation journey product.
    Created by admins (bulk) or submitted by premium users (single, pending review).
    """
    __tablename__ = "liberation_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Unique slug used everywhere (URL, Stripe product, billing plan code)
    journey_code = Column(String, unique=True, nullable=False, index=True)

    title = Column(String, nullable=False)                      # "The Path to Inner Peace"
    description = Column(Text, nullable=True)                   # Shown on the sales page
    cover_image_url = Column(String, nullable=True)             # S3 image for the card
    total_days = Column(Integer, nullable=False)                 # 7, 20, 30 …
    price_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String, default="EUR", nullable=False)

    # Who created it
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    is_admin_created = Column(Boolean, default=False, nullable=False)

    # Moderation (user submissions start as "pending")
    moderation_status = Column(
        Enum(DefinitionStatus), default=DefinitionStatus.pending, nullable=False
    )
    moderation_notes = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)   # Admin can deactivate

    # Async job tracking for AI blueprint generation
    job_id = Column(String, nullable=True, index=True)
    generation_status = Column(
        Enum("processing", "completed", "failed", name="generationstatus_liberation"),
        nullable=True,
    )

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    day_definitions = relationship(
        "LiberationDayDefinition",
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="LiberationDayDefinition.day_number",
    )
    creator = relationship("User", foreign_keys=[created_by])


class LiberationDayDefinition(Base):
    """One row per day inside a LiberationDefinition — stores the theme."""
    __tablename__ = "liberation_day_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("liberation_definitions.id"),
        nullable=False,
        index=True,
    )

    day_number = Column(Integer, nullable=False)   # 1 … N
    day_theme = Column(String, nullable=False)      # "Awakening", "Grounding", etc.

    # Relationships
    definition = relationship("LiberationDefinition", back_populates="day_definitions")


# ============================================================================
# PROGRESS LAYER — a user's personal enrolment and daily progress
# ============================================================================

class UserJourney(Base):
    """Master record proving a user enrolled in a journey."""
    __tablename__ = "user_journeys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Links back to the product catalog
    definition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("liberation_definitions.id"),
        nullable=True,
        index=True,
    )

    # Denormalised for quick access (mirrors definition.journey_code)
    journey_code = Column(String, nullable=False, index=True)
    total_days = Column(Integer, nullable=False, default=7)

    status = Column(Enum(JourneyStatus), default=JourneyStatus.active, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # User's chosen daily reminder time (e.g. "7:30", "9:30")
    reminder_preference = Column(String, nullable=True)

    # Relationships
    definition = relationship("LiberationDefinition", foreign_keys=[definition_id])
    steps = relationship(
        "UserJourneyStep",
        back_populates="journey",
        cascade="all, delete-orphan",
        order_by="UserJourneyStep.day_number",
    )


class UserJourneyStep(Base):
    """Tracks a single day within a journey — inputs, AI output, and reflections."""
    __tablename__ = "user_journey_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journey_id = Column(UUID(as_uuid=True), ForeignKey("user_journeys.id"), nullable=False, index=True)

    day_number = Column(Integer, nullable=False)
    day_theme = Column(String, nullable=True)

    status = Column(Enum(StepStatus), default=StepStatus.locked, nullable=False)

    # ── Pre-exercise input ──
    morning_feeling = Column(Text, nullable=True)

    # ── AI-generated exercise content ──
    ai_greeting = Column(Text, nullable=True)
    ai_exercise_text = Column(Text, nullable=True)
    ai_why_text = Column(Text, nullable=True)

    # ── Post-exercise reflection ──
    energy_level_after = Column(Integer, nullable=True)
    reflection_opened = Column(Text, nullable=True)
    reflection_takeaway = Column(Text, nullable=True)

    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    journey = relationship("UserJourney", back_populates="steps")
