"""
app/schemas/schema_rag.py
Pydantic models for the RAG pipeline: ingestion and book recommendation endpoints.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ---------------------------------------------------------------------------
# Story type filter — re-exported for convenience
# ---------------------------------------------------------------------------

class StoryTypeFilter(str, Enum):
    confession = "confession"
    meditation = "meditation"
    transformation = "transformation"
    all = "all"


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class IngestAllResponse(BaseModel):
    total_stories_indexed: int = Field(
        ..., description="Number of completed stories embedded and upserted into Pinecone"
    )
    message: str = Field(default="Full re-index completed.")


class IngestNewRequest(BaseModel):
    since: Optional[datetime] = Field(
        None,
        description=(
            "Only index stories created after this timestamp. "
            "Defaults to 24 hours ago if omitted."
        ),
    )


class IngestNewResponse(BaseModel):
    new_stories_indexed: int = Field(
        ..., description="Number of new stories embedded and upserted"
    )
    message: str = Field(default="Incremental index completed.")


# ---------------------------------------------------------------------------
# Book Recommendations
# ---------------------------------------------------------------------------

class BookRecommendation(BaseModel):
    title: str = Field(..., description="Title of the recommended book")
    author: str = Field(..., description="Author of the recommended book")
    reason: str = Field(
        ..., description="Why this book matches the user's profile and story engagement"
    )


class BookRecommendationsResponse(BaseModel):
    recommendations: List[BookRecommendation] = Field(
        ..., description="List of personalised book recommendations"
    )
    source: str = Field(
        default="rag",
        description="'rag' if personalised via vector search, 'random' if fallback",
    )
