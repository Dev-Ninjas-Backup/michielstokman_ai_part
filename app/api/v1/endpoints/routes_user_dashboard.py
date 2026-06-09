"""
routes_user_dashboard.py
User-facing dashboard endpoints — includes RAG-powered book recommendations
and story detail view.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_user, get_current_user_optional, enforce_guest_story_limit
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
from app.utils.media import format_media_url

router = APIRouter()


# ---------------------------------------------------------------------------
# Discovery Feed
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/feed",
    response_model=ApiResponse[DiscoveryFeedResponse],
)
def get_discovery_feed(
    story_type: Optional[List[str]] = Query(None, description="Filter by 'confession', 'meditation', or 'transformation' (can provide multiple)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Returns the main story grid for the discovery page.
    Injects the Premium Liberation Journey card along with standard stories.
    Supports filtering by one or more story types.
    """
    # 1. Parse multiple types (handles both ?story_type=a&story_type=b and ?story_type=a,b)
    requested_types = []
    if story_type:
        for t in story_type:
            requested_types.extend([item.strip() for item in t.split(",") if item.strip()])

    from app.model.user import User
    from app.model.profile import UserProfile
    from app.model.story import Story
    user_count = db.query(User).count()
    country_count = db.query(func.count(func.distinct(UserProfile.country))).scalar() or 0
    story_count = db.query(Story).filter(Story.generation_status == GenerationStatus.completed).count()
    
    hero_stats = {
        "total_users": user_count,
        "total_countries": country_count,
        "total_stories_generated": story_count
    }

    # 3. Fetch approved stories for the grid
    query = (
        db.query(story_data.Story)
        .filter(story_data.Story.generation_status == GenerationStatus.completed)
        .filter(story_data.Story.moderation_status == ModerationStatus.approved)
    )

    if requested_types:
        query = query.filter(story_data.Story.story_type.in_(requested_types))

    stories = query.order_by(story_data.Story.created_at.desc()).limit(20).all()

    # 4. Fetch latest category images for fallbacks (cached for this request)
    from app.data import cover_image as cover_data
    from app.model.cover_image import CoverImageType
    
    fallback_images = {
        "confession": cover_data.get_latest_active_image_url(db, CoverImageType.confession),
        "meditation": cover_data.get_latest_active_image_url(db, CoverImageType.meditation),
        "transformation": cover_data.get_latest_active_image_url(db, CoverImageType.transformation),
    }

    items = []
    
    # 5. Process stories into feed items
    from app.utils.messages import STORY_UNTITLED
    for s in stories:
        s_type = s.story_type.value if s.story_type else "confession"

        # Resolve author/display name
        author_display = s.first_name
        if not author_display and s.user and s.user.profile:
            author_display = s.user.profile.true_name
        if not author_display and s.user:
            author_display = s.user.email

        # Get actual average star rating from StoryFeedback
        from app.model.feedback import StoryFeedback
        rating_stats = (
            db.query(func.avg(StoryFeedback.star_rating).label("avg_rating"))
            .filter(StoryFeedback.story_id == s.id)
            .first()
        )
        feed_rating = round(float(rating_stats.avg_rating), 1) if rating_stats.avg_rating else (round(s.pulse_score / 20.0, 1) if (s.pulse_score and s.pulse_score > 0) else None)

        items.append(StoryFeedItem(
            id=str(s.id),
            title=s.title or STORY_UNTITLED,
            description=(s.story_text[:120] + "...") if s.story_text else None,
            story_type=s_type,
            cover_image_url=format_media_url(s.cover_image_url or fallback_images.get(s_type)),
            audio_path=format_media_url(s.audio_path),
            rating=feed_rating,
            listened_count=s.views_count or 0,
            author_name=author_display,
            is_explicit=False 
        ))

    # 6. Inject the Liberation Journey cards (if not filtering or if specifically looking for journeys)
    if not requested_types or "transformation" in requested_types:
        lib_cards = LiberationService.get_all_feed_cards(db, current_user.id if current_user else None)
        
        for lib_card in lib_cards:
            # Fallback for Journey card image if definition doesn't have one
            if not lib_card.get("cover_image_url"):
                lib_card["cover_image_url"] = fallback_images.get("transformation")
                
            lib_card["cover_image_url"] = format_media_url(lib_card.get("cover_image_url"))
                
            # Inject at position 3, then 4, 5 etc, or at the end if not enough items
            if len(items) >= 3:
                items.insert(2, lib_card)
            else:
                items.append(lib_card)

    result = DiscoveryFeedResponse(hero_stats=hero_stats, items=items)
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

    from app.utils.messages import STORY_GENERATION_CREDIT_REMAINING, STORY_GENERATION_PREMIUM_UNLIMITED
    from datetime import datetime, timedelta, timezone
    
    next_reset = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    if is_premium:
        result = CreditStatusResponse(
            is_premium=True,
            daily_credits_remaining=-1,
            max_daily_credits=-1,
            next_reset_at=None,
            message=STORY_GENERATION_PREMIUM_UNLIMITED,
        )
    else:
        credit = credit_data.get_or_create_credit(db, str(current_user.id))
        result = CreditStatusResponse(
            is_premium=False,
            daily_credits_remaining=credit.daily_credits_remaining,
            max_daily_credits=credit.max_daily_credits,
            next_reset_at=next_reset,
            message=STORY_GENERATION_CREDIT_REMAINING.format(
                remaining=credit.daily_credits_remaining,
                max=credit.max_daily_credits
            ),
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
    auth_ctx: dict = Depends(enforce_guest_story_limit),
):
    """
    Returns full story details for the detail/player page.

    Includes the story content, audio path, and aggregated feedback stats
    (average rating, average resonance score, total reflections, top tags).
    Only returns approved stories to regular users.

    **Guests** can call this endpoint with a guest token but are limited
    to one story per day.
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

    # Increment listened/views count
    story.views_count = (story.views_count or 0) + 1
    db.commit()

    # Record guest access so the daily limit is enforced on subsequent calls
    if auth_ctx["is_guest"]:
        from datetime import date
        from app.model.guest_session import GuestSession
        session = db.query(GuestSession).filter_by(id=auth_ctx["guest_id"]).first()
        if session:
            session.last_story_date = date.today()
            session.last_story_id = str(story.id)
            db.commit()

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

    # --- Resolve admin-managed cover image for this story type ---
    from app.data import cover_image as cover_data
    from app.model.cover_image import CoverImageType
    s_type = story.story_type.value if story.story_type else "confession"
    try:
        cover_type = CoverImageType(s_type)
        cover_image_url = cover_data.get_latest_active_image_url(db, cover_type)
    except (ValueError, Exception):
        cover_image_url = None

    # --- Resolve author name ---
    author_name = story.first_name
    if not author_name and story.user and story.user.profile:
        author_name = story.user.profile.true_name
    
    if not author_name and story.user:
        author_name = story.user.email

    from app.utils.messages import STORY_UNTITLED
    result = StoryDetailUserResponse(
        id=str(story.id),
        title=story.title or STORY_UNTITLED,
        story_type=s_type,
        story_text=story.story_text,
        audio_path=format_media_url(story.audio_path),
        cover_image_url=format_media_url(cover_image_url),
        author_name=author_name,
        voice_name=story.voice_name,
        track_id=story.track_id,
        high_intensity=story.high_intensity,
        is_explicit=False, # Defaulting to false as per previous discovery feed logic
        listened_count=story.views_count or 0,
        audio_duration_seconds=story.audio_duration_seconds,
        created_at=story.created_at.isoformat(),
        avg_rating=avg_rating,
        avg_resonance=avg_resonance,
        total_reflections=total_reflections,
        top_tags=top_tags,
    )
    return success_response("Story details fetched", status.HTTP_200_OK, result)
