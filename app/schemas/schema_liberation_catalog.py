"""
app/schemas/schema_liberation_catalog.py

Pydantic models for Liberation Definition (product catalog) API contracts.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Day theme (used inside requests and responses) ──────────────────────────

class DayThemeItem(BaseModel):
    day_number: int
    day_theme: str

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
    total_days: int = Field(..., ge=1, le=365)
    price_cents: int = Field(default=4700, ge=0)
    currency: str = Field(default="EUR", max_length=3)
    day_themes: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of themes, one per day. Length MUST equal total_days.",
    )


class BulkCreateLiberationRequest(BaseModel):
    """Admin-only: create multiple definitions at once."""
    definitions: list[CreateLiberationRequest] = Field(..., min_length=1)


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
    currency: str
    is_admin_created: bool
    moderation_status: str
    moderation_notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    day_themes: list[DayThemeItem] = []

    class Config:
        from_attributes = True


class LiberationCatalogListResponse(BaseModel):
    definitions: list[LiberationDefinitionResponse]
    total: int


class LiberationReviewResponse(BaseModel):
    message: str
    definition_id: UUID
    status: str
