"""
app/schemas/schema_liberation_catalog.py

Pydantic models for Liberation Definition (product catalog) API contracts.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Day theme (used inside requests and responses) ──────────────────────────

class DayDefinitionInput(BaseModel):
    title: str = Field(..., description="Corresponds to the day's theme/title")
    exercise_text: Optional[str] = Field(None, description="What to do")
    why_text: Optional[str] = Field(None, description="Why this exercise")

class DayThemeItem(BaseModel):
    day_number: int
    day_theme: str
    exercise_text: Optional[str] = None
    why_text: Optional[str] = None

    class Config:
        from_attributes = True


# ── Requests ────────────────────────────────────────────────────────────────

class CreateLiberationRequest(BaseModel):
    """
    Single creation — used by BOTH admin and premium users.
    The caller only needs to provide the journey blueprint;
    the route decides if it is auto-approved (admin) or pending (user).
    """
    journey_code: str = Field(..., min_length=2, max_length=100, example="inner_peace")
    title: str = Field(..., min_length=3, max_length=300, example="The Path to Inner Peace")
    description: Optional[str] = Field(None, max_length=5000)
    price_cents: int = Field(default=4700, ge=0)
    currency: str = Field(default="EUR", max_length=3)
    # Visual / card fields — admin can set these on creation
    rating: Optional[float] = Field(None, ge=0, le=5, description="Journey rating shown on the card")
    what_to_expect: Optional[list[str]] = Field(None, description="Bullet points for 'What to Expect' section")
    setup_instructions: Optional[list[str]] = Field(None, description="'Before You Begin' checklist items")
    
    day_1: DayDefinitionInput
    day_2: DayDefinitionInput
    day_3: DayDefinitionInput
    day_4: DayDefinitionInput
    day_5: DayDefinitionInput
    day_6: DayDefinitionInput
    day_7: DayDefinitionInput

    def get_days_list(self) -> list[DayDefinitionInput]:
        return [self.day_1, self.day_2, self.day_3, self.day_4, self.day_5, self.day_6, self.day_7]


class BulkCreateLiberationRequest(BaseModel):
    """Admin-only: create multiple definitions at once."""
    definitions: list[CreateLiberationRequest] = Field(..., min_length=1)


class UpdateLiberationRequest(BaseModel):
    """Admin-only: update an existing liberation definition."""
    title: Optional[str] = Field(None, min_length=3, max_length=300)
    description: Optional[str] = Field(None, max_length=5000)
    price_cents: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    cover_image_url: Optional[str] = None
    is_active: Optional[bool] = None
    rating: Optional[float] = Field(None, ge=0, le=5)
    what_to_expect: Optional[list[str]] = None
    setup_instructions: Optional[list[str]] = None
    day_1: Optional[DayDefinitionInput] = None
    day_2: Optional[DayDefinitionInput] = None
    day_3: Optional[DayDefinitionInput] = None
    day_4: Optional[DayDefinitionInput] = None
    day_5: Optional[DayDefinitionInput] = None
    day_6: Optional[DayDefinitionInput] = None
    day_7: Optional[DayDefinitionInput] = None

    def get_days_dict(self) -> dict[int, DayDefinitionInput]:
        """Returns a map of day_number -> input if provided."""
        mapping = {}
        if self.day_1: mapping[1] = self.day_1
        if self.day_2: mapping[2] = self.day_2
        if self.day_3: mapping[3] = self.day_3
        if self.day_4: mapping[4] = self.day_4
        if self.day_5: mapping[5] = self.day_5
        if self.day_6: mapping[6] = self.day_6
        if self.day_7: mapping[7] = self.day_7
        return mapping


class ReviewLiberationRequest(BaseModel):
    """Admin action to approve or reject a user-submitted definition."""
    action: str = Field(..., pattern="^(approve|reject)$")
    notes: Optional[str] = Field(None, max_length=5000)


# ── Responses ───────────────────────────────────────────────────────────────

class LiberationDefinitionResponse(BaseModel):
    id: UUID
    journey_code: str
    title: str
    description: Optional[str] = None
    total_days: int
    price_cents: int
    price: float
    currency: str
    is_admin_created: bool
    moderation_status: str
    moderation_notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    cover_image_url: Optional[str] = None
    rating: Optional[float] = None
    what_to_expect: list[str] = []
    setup_instructions: list[str] = []
    days: list[DayThemeItem] = []

    class Config:
        from_attributes = True


class LiberationCatalogListResponse(BaseModel):
    definitions: list[LiberationDefinitionResponse]
    total: int


class LiberationReviewResponse(BaseModel):
    message: str
    definition_id: UUID
    status: str
