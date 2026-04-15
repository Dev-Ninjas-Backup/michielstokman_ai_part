"""
routes_user_dashboard.py
User-facing dashboard endpoints — includes RAG-powered book recommendations.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.deps import get_current_user
from app.model.user import User
from app.schemas.schema_rag import (
    BookRecommendationsResponse,
    StoryTypeFilter,
)
from app.services.service_rag import RAGService

router = APIRouter()


# ---------------------------------------------------------------------------
# Book Recommendations (RAG-powered)
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/recommendations",
    response_model=BookRecommendationsResponse,
)
async def get_book_recommendations(
    story_type: StoryTypeFilter = Query(
        StoryTypeFilter.all,
        description=(
            "Filter recommendations by story type: "
            "'confession', 'meditation', 'transformation', or 'all'"
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns personalised book recommendations based on the logged-in user's
    profile and the stories they've engaged with.

    - Uses Pinecone vector search to find the most relevant stories.
    - Passes those to Grok LLM to synthesise tailored book suggestions.
    - Falls back to a curated random selection when no vector matches exist.

    Optional `story_type` query param filters by confession / meditation / transformation.
    """
    try:
        return RAGService.get_book_recommendations(
            db=db,
            user_id=str(current_user.id),
            story_type=story_type,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate book recommendations: {str(e)}",
        )
