"""
app/schemas/schema_feedback.py
Pydantic models for the story feedback/review endpoint.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class StoryFeedbackRequest(BaseModel):
    touch_score: Optional[float] = Field(
        None, ge=0, le=10,
        description="Slider value 0-10: How much did this touch or open something in you?"
    )
    star_rating: Optional[float] = Field(
        None, ge=0, le=5,
        description="Star rating out of 5 (e.g. 4.3)"
    )
    resonance_tags: Optional[List[str]] = Field(
        None,
        description="Tags that resonated, e.g. ['Voice', 'Emotional Arc', 'Liberation Moment']"
    )
    reaction: Optional[str] = Field(
        None,
        description="Quick reaction: 'Love this', 'More like this', 'Too Intense', 'Not my vibe'"
    )
    feedback_text: Optional[str] = Field(
        None,
        description="Free-form text feedback ('Share a thought...')"
    )


class StoryFeedbackResponse(BaseModel):
    id: str
    story_id: str
    user_id: str
    touch_score: Optional[float] = None
    star_rating: Optional[float] = None
    resonance_tags: Optional[List[str]] = None
    reaction: Optional[str] = None
    feedback_text: Optional[str] = None
    message: str = "Feedback submitted successfully."
