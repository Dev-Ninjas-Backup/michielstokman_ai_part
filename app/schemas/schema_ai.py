import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class StoryType(str, Enum):
    confession = "confession"
    meditation = "meditation"
    transformation = "transformation"


class CoverImageMode(str, Enum):
    """Where the story's cover art comes from."""
    ai_generated = "ai_generated"
    user_uploaded = "user_uploaded"


# ---------------------------------------------------------------------------
# Track search
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    track_ids: List[str] = Field(..., description="List of the top 5 relevant track IDs")


# ---------------------------------------------------------------------------
# Resonance (journaling question)
# ---------------------------------------------------------------------------

class ResonanceRequest(BaseModel):
    """
    Input for generating an AI journaling question.
    Matches the 'Resonance Reflection' Figma screen.
    """
    track_id: str = Field(..., description="The ID of the story/track the user listened to")
    touch_score: float = Field(..., description="Slider value 0-10 (How much did this touch you?)")
    star_rating: Optional[float] = Field(None, ge=0, le=5, description="Star rating 0-5 from the Resonance Reflection screen")
    resonance_tags: List[str] = Field(
        default_factory=list, 
        description="Markers selected, e.g. ['Voice', 'Energy Shift', 'Didn't Connect']"
    )
    feedback_text: Optional[str] = Field(
        None, 
        description="The optional 'Share a thought' text from the user"
    )

class ResonanceResponse(BaseModel):
    journaling_question: str = Field(..., description="The generated journaling question")


# ---------------------------------------------------------------------------
# Story generation
# ---------------------------------------------------------------------------

class StoryGenerateRequest(BaseModel):
    """
    Payload for generating a personalised Confession or Meditation.
    Matches the Figma 'Share Your Liberation' and 'Share Your Voice' screens exactly.
    """
    story_type: StoryType = Field(..., description="Type of story: confession or meditation")
    title: Optional[str] = Field(None, description="Title of the submission")
    first_name: Optional[str] = Field(None, description="User's first name")
    story_input: str = Field(..., description="The user's manual story or meditation script")
    
    growth_areas: List[str] = Field(
        default_factory=list, 
        description="Growth areas selected, e.g. ['Fear & Freedom', 'Self-Discovery']"
    )
    life_phase: Optional[str] = Field(None, description="Current life phase, e.g. 'Deepening'")
    tags: List[str] = Field(
        default_factory=list, 
        description="Comma-separated tags converted to a list"
    )

    # Toggle for 'Contains sensitive content'
    high_intensity: bool = Field(
        False, 
        description="Toggle for high intensity/explicit content (True = Activated, False = Off)"
    )

    # Narration voice — see GET /v1/voices for the selectable options.
    voice_name: Optional[str] = Field(
        None,
        description="Narration voice to use. Omit to auto-select one matching the profile.",
    )
    use_custom_voice: bool = Field(
        False,
        description="Narrate with the member's own cloned voice (requires an uploaded recording)",
    )
    skip_narration: bool = Field(
        False,
        description="True when the member uploaded a finished narration; skip ElevenLabs TTS.",
    )

    # Cover art — AI draws it from the story, or the member supplies their own
    # in the same request as a multipart `image` file.
    image_mode: CoverImageMode = Field(
        CoverImageMode.ai_generated,
        description=(
            "'ai_generated' draws cover art from the story content. "
            "'user_uploaded' uses the image file sent with this request "
            "(multipart field name `image`)."
        ),
    )

    @field_validator("voice_name")
    @classmethod
    def validate_voice_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        from app.core.llm import MEMBER_VOICE_NAMES, canonical_voice_name

        canonical = canonical_voice_name(v)
        if not canonical:
            raise ValueError(
                f"Unknown voice '{v}'. Choose one of: {', '.join(MEMBER_VOICE_NAMES)}."
            )
        return canonical

    @classmethod
    def from_multipart(cls, form) -> "StoryGenerateRequest":
        """Builds a request from a multipart form so the image can travel with it."""
        return cls.model_validate(_form_to_generate_dict(form))


def _form_value(form, name: str) -> Optional[str]:
    value = form.get(name)
    if value is None or value == "":
        return None
    if hasattr(value, "filename"):
        return None
    return str(value)


def _form_bool(form, name: str, default: bool = False) -> bool:
    raw = _form_value(form, name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _form_list(form, name: str) -> List[str]:
    getter = getattr(form, "getlist", None)
    raw_values = getter(name) if getter else [form.get(name)]
    items: List[str] = []
    for raw in raw_values:
        if raw is None or raw == "" or hasattr(raw, "filename"):
            continue
        text = str(raw).strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                items.extend(str(item).strip() for item in parsed if str(item).strip())
                continue
        if "," in text and not text.startswith("["):
            items.extend(part.strip() for part in text.split(",") if part.strip())
            continue
        items.append(text)
    return items


def _form_to_generate_dict(form) -> Dict[str, Any]:
    return {
        "story_type": _form_value(form, "story_type"),
        "title": _form_value(form, "title"),
        "first_name": _form_value(form, "first_name"),
        "story_input": _form_value(form, "story_input"),
        "growth_areas": _form_list(form, "growth_areas"),
        "life_phase": _form_value(form, "life_phase"),
        "tags": _form_list(form, "tags"),
        "high_intensity": _form_bool(form, "high_intensity"),
        "voice_name": _form_value(form, "voice_name"),
        "use_custom_voice": _form_bool(form, "use_custom_voice"),
        "skip_narration": _form_bool(form, "skip_narration"),
        "image_mode": _form_value(form, "image_mode") or CoverImageMode.ai_generated,
    }


def multipart_image(form) -> Optional[Any]:
    """Returns the uploaded cover file, or None when the field was left empty."""
    image = form.get("image")
    if image is None or not getattr(image, "filename", None):
        return None
    return image


def multipart_audio(form) -> Optional[Any]:
    """Returns the member's finished narration file, or None when omitted."""
    audio = form.get("audio")
    if audio is None or not getattr(audio, "filename", None):
        return None
    return audio


class StoryGenerateResponse(BaseModel):
    story_id: str = Field(..., description="UUID of the newly created Story row")
    story_number: Optional[int] = Field(None, description="Sequential story number")
    story_reference: Optional[str] = Field(
        None, description="Human-readable story number, e.g. 'TTL-000042'"
    )
    job_id: str = Field(..., description="Async job ID — poll /admin/ai/status/{job_id} for audio_path")
    voice_name: Optional[str] = Field(None, description="Voice selected for narration")
    image_mode: CoverImageMode = Field(
        CoverImageMode.ai_generated,
        description=(
            "Cover art source. 'user_uploaded' means the image was sent with this "
            "request; 'ai_generated' means artwork is drawn after the story is written."
        ),
    )
    cover_image_url: Optional[str] = Field(
        None,
        description="Set immediately when the member uploaded their own cover.",
    )
    title: Optional[str] = Field(None, description="The title of the generated story")
    story_text: str = Field(..., description="The fully generated story text")
    audio_path: Optional[str] = Field(
        None,
        description="Local path or S3 URL to the audio file once TTS is complete"
    )
    message: str = Field(default="Story generation queued. Audio is being processed.")

    @field_validator("cover_image_url", mode="after")
    @classmethod
    def format_cover(cls, v):
        from app.utils.media import format_media_url

        return format_media_url(v)


# ---------------------------------------------------------------------------
# Bulk / admin generation
# ---------------------------------------------------------------------------

class BulkGenerateRequest(BaseModel):
    topic: str = Field(..., description="The main topic for the generated content")
    story_type: StoryType = Field(..., description="Type of story to generate in bulk")
    format: str = Field(default="audio_script", description="Output format, e.g. 'audio_script'")


class SubmissionGenerateRequest(BaseModel):
    submission_id: str = Field(..., description="The unique ID of the user submission")


# ---------------------------------------------------------------------------
# Async job tracking
# ---------------------------------------------------------------------------

class JobResponse(BaseModel):
    job_id: str = Field(..., description="The unique identifier for the async job")
    message: str = Field(..., description="Confirmation message")

class JobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(..., description="Current status: 'processing', 'completed', 'failed'")
    title: Optional[str] = Field(None, description="The title of the generated story")
    audio_path: Optional[str] = Field(None, description="Set once audio generation is complete")
    story_text: Optional[str] = Field(None, description="The text of the generated story")

