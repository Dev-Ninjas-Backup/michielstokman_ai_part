"""
app/schemas/schema_member_story.py
Pydantic contracts for the member-facing story workspace: voice selection,
own-library management, edit + regenerate, and Meta/Spotify distribution copy.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.schema_ai import StoryType
from app.schemas.schema_system import PaginationMeta
from app.utils.media import format_media_url


# ---------------------------------------------------------------------------
# Voice selection
# ---------------------------------------------------------------------------

class VoiceOption(BaseModel):
    name: str = Field(..., description="Identifier to pass back as `voice_name`")
    label: str = Field(..., description="Display name for the voice picker")
    gender: str
    language: str
    description: str
    is_custom: bool = Field(False, description="True for the member's own cloned voice")
    preview_url: Optional[str] = Field(
        None, description="Short MP3 the member can play before choosing this voice"
    )
    preview_text: Optional[str] = Field(
        None, description="The line spoken in the preview clip"
    )

    @field_validator("preview_url", mode="after")
    @classmethod
    def format_preview(cls, v):
        return format_media_url(v)


class VoiceCatalogResponse(BaseModel):
    voices: List[VoiceOption] = Field(..., description="Predefined narration voices")
    custom_voice: Optional[VoiceOption] = Field(
        None, description="The member's cloned voice, if they have recorded one"
    )
    default_voice: str = Field(..., description="Voice used when none is chosen")


class CustomVoiceResponse(BaseModel):
    has_custom_voice: bool
    voice_name: Optional[str] = None
    created_at: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Member story library
# ---------------------------------------------------------------------------

class MemberStoryListItem(BaseModel):
    id: str
    story_number: Optional[int] = None
    story_reference: Optional[str] = Field(
        None, description="Human-readable story number, e.g. 'TTL-000042'"
    )
    title: Optional[str] = None
    excerpt: Optional[str] = Field(
        None,
        description=(
            "Short single-line preview of the narrated story, for feed and library "
            "cards. Null while the story is still generating. The full text is on "
            "GET /v1/me/stories/{story_id}."
        ),
    )
    story_type: str
    cover_image_url: Optional[str] = None
    audio_path: Optional[str] = None
    voice_name: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    generation_status: str
    moderation_status: str
    submission_status: str
    submission_mode: Optional[str] = Field(
        None,
        description="'studio' rewrites and narrates. 'human_ready' keeps submitted text and audio.",
    )
    has_social_intros: bool = False
    moderation_notes: Optional[str] = None
    created_at: str

    @field_validator("cover_image_url", "audio_path", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)


class MemberStoryDetail(MemberStoryListItem):
    member_title: Optional[str] = Field(
        None, description="Title the member submitted on create or edit"
    )
    ai_generated_title: Optional[str] = Field(
        None, description="Title produced by the LLM during generation"
    )
    use_ai_title: bool = Field(
        False,
        description="When true, `title` reflects `ai_generated_title` instead of `member_title`",
    )
    story_text: Optional[str] = Field(None, description="The AI-narrated story text")
    story_input: Optional[str] = Field(
        None, description="The member's own original submission, before AI processing"
    )
    first_name: Optional[str] = None
    location: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    age: Optional[int] = None
    growth_areas: Optional[List[str]] = None
    life_phase: Optional[str] = None
    tags: Optional[List[str]] = None
    high_intensity: bool = False
    uses_custom_voice: bool = False
    image_source: Optional[str] = None
    alignment: Optional[List[Dict[str, Any]]] = None
    social_intros: Optional[Dict[str, str]] = None
    regeneration_count: int = 0
    withdrawn_at: Optional[str] = None


class MemberStoryListResponse(BaseModel):
    stories: List[MemberStoryListItem]
    counts: Dict[str, int] = Field(
        ..., description="Story counts keyed by submission status, plus 'all'"
    )
    meta: PaginationMeta


# ---------------------------------------------------------------------------
# Edit / regenerate / re-narrate
# ---------------------------------------------------------------------------

class UpdateMemberStoryRequest(BaseModel):
    """
    Edits a member's own story. Any field left unset keeps its current value.

    When `regenerate` is true the edited input is pushed back through the AI
    prompt and re-narrated, and the story returns to `processing` until the
    background job finishes.
    """
    title: Optional[str] = None
    story_input: Optional[str] = Field(
        None, description="The member's rewritten source text"
    )
    use_ai_title: Optional[bool] = Field(
        None,
        description=(
            "Switch the active title to the AI-generated one (true) or the member's "
            "own (false). Requires ai_generated_title to be set when true."
        ),
    )
    story_type: Optional[StoryType] = None
    growth_areas: Optional[List[str]] = None
    life_phase: Optional[str] = None
    tags: Optional[List[str]] = None
    high_intensity: Optional[bool] = None
    voice_name: Optional[str] = Field(
        None, description="Narration voice to use for the regenerated audio"
    )
    use_custom_voice: Optional[bool] = Field(
        None, description="Narrate with the member's own cloned voice"
    )
    regenerate: bool = Field(
        True,
        description="Re-run the AI prompt and narration. Set false to only correct metadata.",
    )


class RenarrateRequest(BaseModel):
    """Re-records the existing story text with a different voice. Text is untouched."""
    voice_name: Optional[str] = Field(
        None, description="One of the names from GET /v1/voices"
    )
    use_custom_voice: bool = Field(
        False, description="Narrate with the member's own cloned voice instead"
    )


class StoryJobAcceptedResponse(BaseModel):
    story_id: str
    story_reference: Optional[str] = None
    job_id: str
    generation_status: str
    message: str


class WithdrawStoryResponse(BaseModel):
    story_id: str
    story_reference: Optional[str] = None
    submission_status: str
    message: str


# ---------------------------------------------------------------------------
# Imagery
# ---------------------------------------------------------------------------

class StoryImageResponse(BaseModel):
    story_id: str
    cover_image_url: Optional[str] = None
    image_source: Optional[str] = None
    message: str

    @field_validator("cover_image_url", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)


# ---------------------------------------------------------------------------
# Meta / Spotify distribution
# ---------------------------------------------------------------------------

class SocialIntros(BaseModel):
    instagram: str = Field(..., description="Short teaser-style introduction")
    facebook: str = Field(..., description="Short teaser-style introduction")
    spotify: str = Field(..., description="Longer introduction suited to the platform")


class SharePackageResponse(BaseModel):
    """Everything a client needs to publish a story to Meta or Spotify."""
    story_id: str
    story_number: Optional[int] = None
    story_reference: Optional[str] = None
    title: Optional[str] = None
    story_type: str
    author_name: Optional[str] = None
    cover_image_url: Optional[str] = Field(
        None, description="The existing website/PWA artwork for this piece"
    )
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    share_url: Optional[str] = Field(None, description="Public listing URL on the web app")
    intros: SocialIntros
    generated_at: Optional[str] = None

    @field_validator("cover_image_url", "audio_url", mode="after")
    @classmethod
    def format_media(cls, v):
        return format_media_url(v)
