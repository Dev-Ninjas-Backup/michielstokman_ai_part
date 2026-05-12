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
    """
    Input for generating an AI journaling question.
    Matches the 'Resonance Reflection' Figma screen.
    """
    track_id: str = Field(..., description="The ID of the story/track the user listened to")
    touch_score: float = Field(..., description="Slider value 0-10 (How much did this touch you?)")
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

