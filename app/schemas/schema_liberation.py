"""
app/schemas/schema_liberation.py

Pydantic models for Liberation Journey API request/response contracts.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Step detail (used inside responses) ─────────────────────────────────────

class StepSummary(BaseModel):
    day_number: int
    day_theme: str
    status: str  # "locked" | "available" | "completed"
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StepDetail(BaseModel):
    day_number: int
    day_theme: str
    status: str
    morning_feeling: Optional[str] = None
    ai_greeting: Optional[str] = None
    ai_exercise_text: Optional[str] = None
    ai_why_text: Optional[str] = None
    audio_url: Optional[str] = None
    energy_level_after: Optional[int] = None
    reflection_opened: Optional[str] = None
    reflection_takeaway: Optional[str] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Journey status response ────────────────────────────────────────────────

class JourneyStatusResponse(BaseModel):
    journey_id: UUID
    journey_code: str
    status: str  # "active" | "completed" | "abandoned"
    total_days: int
    current_day: int  # highest available day
    steps: list[StepSummary]

    class Config:
        from_attributes = True


# ── Requests ────────────────────────────────────────────────────────────────

class DayCheckinRequest(BaseModel):
    """Payload for the pre-exercise screen: 'How are you feeling this morning?'"""
    morning_feeling: str = Field(..., min_length=1, max_length=2000)


class DayCompleteRequest(BaseModel):
    """Payload for the post-exercise reflection screen."""
    energy_level: int = Field(..., ge=0, le=10)
    what_opened: str = Field(..., min_length=1, max_length=5000)
    key_takeaway: str = Field(..., min_length=1, max_length=5000)


# ── Responses ───────────────────────────────────────────────────────────────

class DayGenerateResponse(BaseModel):
    day_number: int
    day_theme: str
    ai_greeting: str
    ai_exercise_text: str
    ai_why_text: str
    audio_url: Optional[str] = None


class DayCompleteResponse(BaseModel):
    day_number: int
    status: str
    message: str
    next_day_available: bool


class JourneyCompleteResponse(BaseModel):
    message: str
    total_days_completed: int


# ── Discovery feed card ─────────────────────────────────────────────────────

class LiberationFeedCard(BaseModel):
    """
    The premium journey card injected into the general story discovery grid.
    If is_enrolled=False → shows price + "Begin Your Liberation" CTA.
    If is_enrolled=True  → shows progress + "Continue" CTA.
    """
    card_type: str = "liberation_journey"
    journey_code: str = "vitality_7_days"
    title: str = "Feel More Vital – 7 Days to More Life Energy"
    description: str = "7 gentle daily practices to release tension, boost vitality, and feel genuinely alive again."
    price_display: str = "€47"
    price_cents: int = 4700
    total_days: int = 7
    is_enrolled: bool = False
    current_day: Optional[int] = None
    journey_status: Optional[str] = None  # "active" | "completed" | None
    journey_id: Optional[UUID] = None
