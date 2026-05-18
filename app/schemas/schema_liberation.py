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
    energy_level_after: Optional[float] = None
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

class EnrollJourneyRequest(BaseModel):
    """Payload to enroll in a journey with customizable day counts and reminder time."""
    journey_code: str = Field(..., example="vitality")
    total_days: int = Field(default=7, ge=1, le=100)
    reminder_preference: Optional[str] = Field(None, example="7:30")


class DayCheckinRequest(BaseModel):
    """Payload for the pre-exercise screen: 'How are you feeling this morning?'"""
    morning_feeling: str = Field(default="", max_length=2000, description="How the user is feeling this morning")


class DayCompleteRequest(BaseModel):
    """Payload for the post-exercise reflection screen."""
    energy_level: float = Field(default=5.0, ge=0.0, le=10.0, description="Energy level after exercise (0-10)")
    what_opened: str = Field(default="", max_length=5000, description="What opened up during the exercise")
    key_takeaway: str = Field(default="", max_length=5000, description="Key takeaway from the exercise")


# ── Responses ───────────────────────────────────────────────────────────────

class DayGenerateResponse(BaseModel):
    day_number: int
    day_theme: str
    ai_greeting: str
    ai_exercise_text: str
    ai_why_text: str


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
    journey_code: str
    title: str
    description: str
    cover_image_url: Optional[str] = None
    price_display: int
    price_cents: int
    total_days: int
    rating: Optional[float] = None
    what_to_expect: list[str] = []
    setup_instructions: list[str] = []
    is_enrolled: bool = False
    has_access: bool = False
    current_day: Optional[int] = None
    journey_status: Optional[str] = None  # "active" | "completed" | None
    journey_id: Optional[UUID] = None


class PurchasedJourneyItem(BaseModel):
    journey_code: str
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    total_days: int
    is_enrolled: bool
    current_day: Optional[int] = None
    status: str  # "active" | "purchased" | "completed"

class PurchasedJourneysResponse(BaseModel):
    journeys: list[PurchasedJourneyItem]
    total: int
