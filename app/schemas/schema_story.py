"""
app/schemas/schema_story.py
Pydantic models for story-related endpoints (moderation + user-facing detail).
"""
from pydantic import BaseModel, UUID4, field_validator
from typing import Optional, List
from app.utils.media import format_media_url


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
    first_name: str | None
    story_input: str | None
    growth_areas: list[str] | None
    life_phase: str | None
    tags: list[str] | None

    @field_validator("audio_path", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)


class StoryListItemResponse(BaseModel):
    id: UUID4
    title: str | None
    story_type: str
    author: str | None
    created_at: str
    moderation_status: str
    cover_image_url: str | None

    @field_validator("cover_image_url", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)


from app.schemas.schema_system import PaginationMeta


class ModerationQueueResponse(BaseModel):
    stories: list[StoryListItemResponse]
    all: int
    pending: int
    flagged: int
    approved: int
    rejected: int
    meta: PaginationMeta



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
    cover_image_url: Optional[str] = None  # Admin-managed category image
    author_name: Optional[str] = None
    voice_name: Optional[str] = None
    track_id: Optional[str] = None
    high_intensity: bool = False
    is_explicit: bool = False
    listened_count: int = 0
    audio_duration_seconds: Optional[int] = None
    created_at: str

    # Aggregated feedback stats (from StoryFeedback table)
    avg_rating: Optional[float] = None
    avg_resonance: Optional[float] = None
    total_reflections: int = 0
    top_tags: List[str] = []

    @field_validator("audio_path", "cover_image_url", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)
