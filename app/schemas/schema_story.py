"""
app/schemas/schema_story.py
Pydantic models for story-related endpoints (moderation + user-facing detail).
"""
from pydantic import BaseModel, UUID4, field_validator
from typing import Optional, List, Dict, Any
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
    location: str | None = None
    gender: str | None = None
    sexual_orientation: str | None = None
    occupation: str | None = None
    age: int | None = None
    background: str | None = None
    personality: str | None = None
    lifestyle: str | None = None
    situation: str | None = None
    submission_mode: str | None = None
    hero_hook: str | None = None
    hero_tagline: str | None = None
    editorial_brief: str | None = None
    story_input: str | None
    growth_areas: list[str] | None
    life_phase: str | None
    tags: list[str] | None
    high_intensity: bool = False
    voice_name: str | None = None
    voice_id: str | None = None
    cover_image_url: str | None = None

    @field_validator("audio_path", "cover_image_url", mode="after")
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
    hero_hook: Optional[str] = None
    hero_tagline: Optional[str] = None
    first_name: Optional[str] = None
    location: Optional[str] = None
    gender: Optional[str] = None
    sexual_orientation: Optional[str] = None
    occupation: Optional[str] = None
    age: Optional[int] = None
    tags: Optional[List[str]] = None
    growth_areas: Optional[List[str]] = None
    life_phase: Optional[str] = None
    high_intensity: Optional[bool] = None
    editorial_brief: Optional[str] = None
    voice_name: Optional[str] = None


class ApproveStoryRequest(BaseModel):
    notes: Optional[str] = None


class SuggestFieldRequest(BaseModel):
    field: str

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed = {"hook", "tagline", "moods", "analysis", "voice"}
        value = (v or "").strip().lower()
        if value not in allowed:
            raise ValueError(f"field must be one of {sorted(allowed)}")
        return value


class SuggestFieldResponse(BaseModel):
    field: str
    hero_hook: Optional[str] = None
    hero_tagline: Optional[str] = None
    tags: Optional[List[str]] = None
    growth_areas: Optional[List[str]] = None
    life_phase: Optional[str] = None
    editorial_brief: Optional[str] = None
    voice_name: Optional[str] = None
    voice_id: Optional[str] = None


class RequestChangesRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        text = (v or "").strip()
        if not text:
            raise ValueError("reason is required")
        return text


class RequestChangesResponse(BaseModel):
    message: str
    story_id: UUID4
    status: str


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
    location: Optional[str] = None
    gender: Optional[str] = None
    sexual_orientation: Optional[str] = None
    occupation: Optional[str] = None
    age: Optional[int] = None
    hero_hook: Optional[str] = None
    hero_tagline: Optional[str] = None
    voice_name: Optional[str] = None
    track_id: Optional[str] = None
    high_intensity: bool = False
    is_explicit: bool = False
    listened_count: int = 0
    audio_duration_seconds: Optional[int] = None
    alignment: Optional[List[Dict[str, Any]]] = None
    created_at: str

    # Aggregated feedback stats (from StoryFeedback table)
    avg_rating: Optional[float] = None
    avg_resonance: Optional[float] = None
    total_reflections: int = 0
    tags: List[str] = []
    top_tags: List[str] = []

    @field_validator("audio_path", "cover_image_url", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)
