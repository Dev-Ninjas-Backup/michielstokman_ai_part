"""
app/schemas/schema_cover_image.py

Pydantic models for the Photo Management (cover image) endpoints.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.model.cover_image import CoverImageType


class CoverImageResponse(BaseModel):
    id: str
    story_type: str
    image_url: str
    is_active: bool
    uploaded_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CoverImageListResponse(BaseModel):
    items: list[CoverImageResponse]
    total: int
    limit: int
    offset: int


class CoverImageUpdateRequest(BaseModel):
    story_type: Optional[CoverImageType] = None
    is_active: Optional[bool] = None
