"""
app/model/liberation.py

Database models for the 7-Day Liberation Journey (premium flow).
Completely isolated from the general `stories` table — each day's
AI text, audio, and user reflections live in `user_journey_steps`.
"""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class JourneyStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class StepStatus(str, enum.Enum):
    locked = "locked"
    available = "available"
    completed = "completed"


# ── 7 fixed day themes for the "Feel More Vital" journey ──
JOURNEY_DAY_THEMES = {
    1: "Awakening",
    2: "Softening",
    3: "Releasing",
    4: "Grounding",
    5: "Flowing",
    6: "Radiating",
    7: "Full Bloom",
}


class UserJourney(Base):
    """Master record proving a user enrolled in a premium journey."""
    __tablename__ = "user_journeys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # e.g. "vitality_7_days" — allows future journey types
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

    # Relationships
    steps = relationship("UserJourneyStep", back_populates="journey", cascade="all, delete-orphan", order_by="UserJourneyStep.day_number")


class UserJourneyStep(Base):
    """Tracks a single day within a journey — inputs, AI output, and reflections."""
    __tablename__ = "user_journey_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journey_id = Column(UUID(as_uuid=True), ForeignKey("user_journeys.id"), nullable=False, index=True)

    # Day number (1 through 7)
    day_number = Column(Integer, nullable=False)
    # Human-readable theme, e.g. "Awakening"
    day_theme = Column(String, nullable=True)

    status = Column(Enum(StepStatus), default=StepStatus.locked, nullable=False)

    # ── Pre-exercise input (Screen 4: "How are you feeling this morning?") ──
    morning_feeling = Column(Text, nullable=True)

    # ── AI-generated exercise content (Screen 5-6) ──
    ai_greeting = Column(Text, nullable=True)        # "Hey friend, let's do something simple..."
    ai_exercise_text = Column(Text, nullable=True)    # The "What to do" block
    ai_why_text = Column(Text, nullable=True)         # The "Why this exercise" explanation
    audio_url = Column(String, nullable=True)          # S3 URL for the AI greeting audio

    # ── Post-exercise reflection (Screen 7: "How did today land?") ──
    energy_level_after = Column(Integer, nullable=True)     # Slider 0-10
    reflection_opened = Column(Text, nullable=True)         # "What opened today?"
    reflection_takeaway = Column(Text, nullable=True)       # "One key takeaway"

    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    journey = relationship("UserJourney", back_populates="steps")
