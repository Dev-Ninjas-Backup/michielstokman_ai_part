"""
app/schemas/schema_admin_chat.py

Pydantic models for the Admin Metrics Chat endpoint.
"""
from typing import Any, Optional
from pydantic import BaseModel, Field


class AdminChatRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The admin's natural-language question about platform metrics.",
        examples=["Top resonance this week", "What are the growth area averages?"],
    )


class AdminChatResponse(BaseModel):
    answer: str
    metrics_snapshot: Optional[dict[str, Any]] = None
