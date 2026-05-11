"""
app/schemas/schema_story.py
Pydantic models for story-related endpoints (moderation + user-facing detail).
"""
from pydantic import BaseModel, UUID4
from typing import Optional, List


# ---------------------------------------------------------------------------
# Admin — Moderation schemas
# ---------------------------------------------------------------------------

class StoryDetailResponse(BaseModel):
    id: UUID4
    title: str | None
    story_type: str
    story_text: str | None
    audio_path: str | None
    author: str | None
    created_at: str
    moderation_status: str
    moderation_notes: str | None
    country_city: str | None
    life_phase: str | None
    relationship_status: str | None
    deepest_desire_fear: str | None
    specific_trigger: str | None
    emotional_context: dict | None


class StoryListItemResponse(BaseModel):
    id: UUID4
    title: str | None
    story_type: str
    author: str | None
    created_at: str
    moderation_status: str
    cover_image_url: str | None


class ModerationQueueResponse(BaseModel):
    stories: list[StoryListItemResponse]
    all: int
    pending: int
    flagged: int
    approved: int
    rejected: int


class UpdateStoryRequest(BaseModel):
    title: Optional[str] = None
    story_type: Optional[str] = None
    story_text: Optional[str] = None


class ApproveStoryResponse(BaseModel):
    message: str
    story_id: UUID4
    status: str


class RejectStoryRequest(BaseModel):
    reason: Optional[str] = None


class RejectStoryResponse(BaseModel):
    message: str
    story_id: UUID4
    status: str


class DeleteStoryResponse(BaseModel):
    message: str
    story_id: UUID4


# ---------------------------------------------------------------------------
# User-facing — Story detail page schemas
# ---------------------------------------------------------------------------

class StoryDetailUserResponse(BaseModel):
    id: str
    title: Optional[str] = None
    story_type: str
    story_text: Optional[str] = None
    audio_path: Optional[str] = None
    track_id: Optional[str] = None
    high_intensity: bool = False
    created_at: str

    # Aggregated feedback stats (from StoryFeedback table)
    avg_rating: Optional[float] = None
    avg_resonance: Optional[float] = None
    total_reflections: int = 0
    top_tags: List[str] = []
