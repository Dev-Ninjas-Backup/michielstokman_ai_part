"""
routes_user_dashboard.py
User-facing dashboard endpoints — includes RAG-powered book recommendations
and story detail view.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_user
from app.model.user import User
from app.model.story import ModerationStatus
from app.model.feedback import StoryFeedback
from app.schemas.schema_rag import (
    BookRecommendationsResponse,
    StoryTypeFilter,
)
from app.schemas.schema_story import StoryDetailUserResponse
from app.schemas.schema_credit import CreditStatusResponse
from app.services.service_rag import RAGService
from app.data import story as story_data
import app.data.credit as credit_data

from app.schemas.schema_user_dashboard import DiscoveryFeedResponse, StoryFeedItem
from app.services.service_liberation import LiberationService
from app.model.story import GenerationStatus

router = APIRouter()


# ---------------------------------------------------------------------------
# Discovery Feed
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/feed",
    response_model=ApiResponse[DiscoveryFeedResponse],
)
def get_discovery_feed(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the main story grid for the discovery page.
    Injects the Premium Liberation Journey card along with standard stories.
    """
    # 1. Fetch some approved stories for the grid
    stories = (
        db.query(story_data.Story)
        .filter(story_data.Story.generation_status == GenerationStatus.completed)
        .filter(story_data.Story.moderation_status == ModerationStatus.approved)
        .order_by(story_data.Story.created_at.desc())
        .limit(12)
        .all()
    )

    items = []
    
    # 2. Add some regular stories
    for s in stories[:5]:
        items.append(StoryFeedItem(
            id=str(s.id),
            title=s.title or "Untitled",
            story_type=s.story_type.value if s.story_type else "confession",
            audio_path=s.audio_path,
        ))

    # 3. Inject the Liberation Journey card
    lib_card = LiberationService.get_feed_card(db, current_user.id)
    items.append(lib_card)

    # 4. Add the rest of the stories
    for s in stories[5:]:
        items.append(StoryFeedItem(
            id=str(s.id),
            title=s.title or "Untitled",
            story_type=s.story_type.value if s.story_type else "confession",
            audio_path=s.audio_path,
        ))

    result = DiscoveryFeedResponse(items=items)
    return success_response("Discovery feed loaded", status.HTTP_200_OK, result)



# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/credits",
    response_model=ApiResponse[CreditStatusResponse],
)
def get_credit_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the user's current credit status.
    Premium users will see is_premium=True with unlimited credits.
    Free users will see their remaining daily credits.
    """
    is_premium = credit_data.is_premium_user(db, str(current_user.id))

    if is_premium:
        result = CreditStatusResponse(
            is_premium=True,
            daily_credits_remaining=-1,
            max_daily_credits=-1,
            message="Premium subscriber — unlimited stories.",
        )
    else:
        credit = credit_data.get_or_create_credit(db, str(current_user.id))
        result = CreditStatusResponse(
            is_premium=False,
            daily_credits_remaining=credit.daily_credits_remaining,
            max_daily_credits=credit.max_daily_credits,
            message=f"{credit.daily_credits_remaining}/{credit.max_daily_credits} credits remaining today.",
        )

    return success_response("Credit status fetched", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# Book Recommendations (RAG-powered)
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/recommendations",
    response_model=ApiResponse[BookRecommendationsResponse],
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
        result = RAGService.get_book_recommendations(
            db=db,
            user_id=str(current_user.id),
            story_type=story_type,
        )
        return success_response("Book recommendations generated", status.HTTP_200_OK, result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate book recommendations: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Story Detail (user-facing)
# ---------------------------------------------------------------------------

@router.get(
    "/stories/{story_id}",
    response_model=ApiResponse[StoryDetailUserResponse],
)
def get_story_detail(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns full story details for the detail/player page.

    Includes the story content, audio path, and aggregated feedback stats
    (average rating, average resonance score, total reflections, top tags).
    Only returns approved stories to regular users.
    """
    story = story_data.get_story_by_id(db, story_id)

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found.",
        )

    # Regular users can only see approved stories
    if story.moderation_status != ModerationStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found.",
        )

    # --- Aggregate feedback stats from StoryFeedback table ---
    stats = (
        db.query(
            func.avg(StoryFeedback.star_rating).label("avg_rating"),
            func.avg(StoryFeedback.touch_score).label("avg_resonance"),
            func.count(StoryFeedback.id).label("total_reflections"),
        )
        .filter(StoryFeedback.story_id == story_id)
        .first()
    )

    avg_rating = round(float(stats.avg_rating), 1) if stats.avg_rating else None
    avg_resonance = round(float(stats.avg_resonance), 1) if stats.avg_resonance else None
    total_reflections = stats.total_reflections or 0

    # --- Top tags: flatten all resonance_tags and count the most common ---
    all_tags_rows = (
        db.query(StoryFeedback.resonance_tags)
        .filter(StoryFeedback.story_id == story_id)
        .filter(StoryFeedback.resonance_tags.isnot(None))
        .all()
    )
    tag_counts: dict[str, int] = {}
    for row in all_tags_rows:
        if row.resonance_tags:
            for tag in row.resonance_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    top_tags = sorted(tag_counts, key=tag_counts.get, reverse=True)[:5]

    result = StoryDetailUserResponse(
        id=str(story.id),
        title=story.title or "Untitled",
        story_type=story.story_type.value if story.story_type else "story",
        story_text=story.story_text,
        audio_path=story.audio_path,
        track_id=story.track_id,
        high_intensity=story.high_intensity,
        created_at=story.created_at.isoformat(),
        avg_rating=avg_rating,
        avg_resonance=avg_resonance,
        total_reflections=total_reflections,
        top_tags=top_tags,
    )
    return success_response("Story details fetched", status.HTTP_200_OK, result)
