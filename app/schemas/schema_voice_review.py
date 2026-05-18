"""
app/schemas/schema_voice_review.py
Pydantic schemas for the Voice Review Admin UI.
"""
from pydantic import BaseModel, UUID4
from typing import Optional


class VoiceReviewItem(BaseModel):
    id: UUID4
    title: Optional[str] = None
    story_type: str
    voice_name: Optional[str] = None
    audio_duration: Optional[str] = None
    created_at: str
    audio_path: Optional[str] = None


from app.schemas.schema_system import PaginationMeta


class VoiceReviewResponse(BaseModel):
    items: list[VoiceReviewItem]
    total: int
    meta: PaginationMeta



class VoiceRegenerateResponse(BaseModel):
    message: str
    story_id: UUID4
    job_id: str
