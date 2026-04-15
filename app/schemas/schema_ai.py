from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class StoryType(str, Enum):
    confession = "confession"
    meditation = "meditation"
    transformation = "transformation"


# ---------------------------------------------------------------------------
# Track search
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    track_ids: List[str] = Field(..., description="List of the top 5 relevant track IDs")


# ---------------------------------------------------------------------------
# Resonance (journaling question)
# ---------------------------------------------------------------------------

class ResonanceRequest(BaseModel):
    track_id: str = Field(..., description="The ID of the track the user is associating with")
    sliders: Dict[str, int] = Field(
        ...,
        description="A dictionary of emotional sliders, e.g. {'tension': 80, 'openness': 30}"
    )

class ResonanceResponse(BaseModel):
    journaling_question: str = Field(..., description="The generated journaling question")


# ---------------------------------------------------------------------------
# Story generation
# ---------------------------------------------------------------------------

class StoryGenerateRequest(BaseModel):
    """
    Payload for generating a personalised Confession, Meditation, or Transformation.
    All user-profile fields are optional — if omitted the story degrades gracefully
    to a warm, non-personalised version. When provided they are injected directly
    into the SuperGrok prompt to ensure every story feels custom-made.
    """
    story_type: StoryType = Field(..., description="Type of story to generate")

    # User profile context (snapshot at request time)
    user_age: Optional[int] = Field(None, description="User's age")
    user_gender: Optional[str] = Field(None, description="User's gender")
    country_city: Optional[str] = Field(None, description="User's country or city")
    life_phase: Optional[str] = Field(None, description="User's current life phase, e.g. 'new mother', 'divorce'")
    relationship_status: Optional[str] = Field(None, description="Relationship status and main dynamic")
    deepest_desire_fear: Optional[str] = Field(None, description="User's deepest desire or fear")
    specific_trigger: Optional[str] = Field(None, description="Specific trigger or situation prompting this story")

    # Priority sliders (0-10 scale) from the user profile
    emotional_sliders: Optional[Dict[str, int]] = Field(
        None,
        description="User's 9 priority sliders, e.g. {'desire_relationship': 8, 'life_purpose': 3, ...}"
    )

    # Session sliders set after listening to a track
    session_sliders: Optional[Dict[str, int]] = Field(
        None,
        description="Emotional sliders from the resonance session, e.g. {'tension': 70, 'openness': 20}"
    )

    # The associated music track (optional)
    track_id: Optional[str] = Field(None, description="ID of the track the user just listened to")

    # High Intensity Toggle (safety/explicitness switch)
    high_intensity: bool = Field(
        False, 
        description="Toggle for high intensity/explicit content (True = Activated, False = Off)"
    )


class StoryGenerateResponse(BaseModel):
    story_id: str = Field(..., description="UUID of the newly created Story row")
    job_id: str = Field(..., description="Async job ID — poll /admin/ai/status/{job_id} for audio_path")
    title: Optional[str] = Field(None, description="The title of the generated story")
    story_text: str = Field(..., description="The fully generated story text")
    audio_path: Optional[str] = Field(
        None,
        description="Local path or S3 URL to the audio file once TTS is complete"
    )
    message: str = Field(default="Story generation queued. Audio is being processed.")


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

