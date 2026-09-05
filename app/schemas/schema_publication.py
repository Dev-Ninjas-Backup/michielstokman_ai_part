from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.schema_system import PaginationMeta


class PublicationListItem(BaseModel):
    id: str
    title: str
    author: Optional[str] = None
    story_type: str
    submitted_at: str
    updated_at: str
    cover_image_url: Optional[str] = None
    content_status: str
    cover_status: str
    voice_status: str
    publication_status: str
    high_intensity: bool = False


class PublicationListData(BaseModel):
    items: list[PublicationListItem]
    all: int = 0
    missing: int = 0
    pending: int = 0
    in_progress: int = 0
    ready_for_review: int = 0
    ready_to_publish: int = 0
    published: int = 0
    rejected: int = 0
    meta: PaginationMeta


class PublicationContact(BaseModel):
    email: Optional[str] = None
    true_name: Optional[str] = None


class PublicationVoice(BaseModel):
    voice_name: Optional[str] = None
    audio_path: Optional[str] = None
    duration_seconds: Optional[int] = None
    generated_at: Optional[str] = None
    voice_not_required: bool = False


class PublicationWorkspace(BaseModel):
    id: str
    title: Optional[str] = None
    story_type: str
    first_name: Optional[str] = None
    location: Optional[str] = None
    gender: Optional[str] = None
    sexual_orientation: Optional[str] = None
    occupation: Optional[str] = None
    age: Optional[int] = None
    high_intensity: bool = False
    story_input: Optional[str] = None
    story_text: Optional[str] = None
    hero_hook: Optional[str] = None
    hero_tagline: Optional[str] = None
    editorial_brief: Optional[str] = None
    tags: Optional[list[str]] = None
    growth_areas: Optional[list[str]] = None
    life_phase: Optional[str] = None
    submission_mode: Optional[str] = None
    cover_image_url: Optional[str] = None
    content_status: str
    cover_status: str
    voice_status: str
    publication_status: str
    can_publish: bool
    publish_blockers: list[str] = Field(default_factory=list)
    submitted_at: str
    updated_at: str
    published_at: Optional[str] = None
    voice: PublicationVoice
    contact: PublicationContact


AssetName = Literal["content", "cover", "voice"]
