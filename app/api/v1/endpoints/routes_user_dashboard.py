"""
routes_user_dashboard.py
User-facing dashboard endpoints — includes RAG-powered book recommendations
and story detail view.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from sqlalchemy.sql.elements import ColumnElement

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_user, get_current_user_optional, enforce_guest_story_limit
from app.model.user import User
from app.model.story import ModerationStatus, SubmissionStatus
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
from app.utils.text import story_card_excerpt

router = APIRouter()

FEED_SORTS = frozenset({"newest", "most_listened", "highest_rated"})


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(part).strip() for part in value if str(part).strip()]


def _jsonb_has_string(column, value: str) -> ColumnElement[bool]:
    """True when a JSONB string array contains `value` as an element."""
    return column.has_key(value) | column.contains([value])


# ---------------------------------------------------------------------------
# Discovery Feed
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard/feed",
    response_model=ApiResponse[DiscoveryFeedResponse],
)
def get_discovery_feed(
    story_type: Optional[List[str]] = Query(None, description="Filter by 'confession', 'meditation', or 'transformation' (can provide multiple)"),
    sort: str = Query("newest", description="newest, most_listened, or highest_rated"),
    hide_explicit: bool = Query(False),
    growth_area: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
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

    sort_key = sort if sort in FEED_SORTS else "newest"
    growth_filter = (growth_area or "").strip() or None
    tag_filter = (tag or "").strip() or None

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

    rating_avg = (
        db.query(
            StoryFeedback.story_id.label("story_id"),
            func.avg(StoryFeedback.star_rating).label("avg_rating"),
        )
        .group_by(StoryFeedback.story_id)
        .subquery()
    )

    query = (
        db.query(story_data.Story, rating_avg.c.avg_rating)
        .outerjoin(rating_avg, story_data.Story.id == rating_avg.c.story_id)
        .filter(story_data.Story.generation_status == GenerationStatus.completed)
        .filter(story_data.Story.moderation_status == ModerationStatus.approved)
        .filter(story_data.Story.submission_status != SubmissionStatus.withdrawn)
    )

    if requested_types:
        query = query.filter(story_data.Story.story_type.in_(requested_types))

    if hide_explicit:
        query = query.filter(story_data.Story.high_intensity.is_(False))

    if growth_filter:
        query = query.filter(_jsonb_has_string(story_data.Story.growth_areas, growth_filter))

    if tag_filter:
        query = query.filter(_jsonb_has_string(story_data.Story.tags, tag_filter))

    if sort_key == "most_listened":
        query = query.order_by(
            story_data.Story.views_count.desc().nullslast(),
            story_data.Story.created_at.desc(),
        )
    elif sort_key == "highest_rated":
        query = query.order_by(
            rating_avg.c.avg_rating.desc().nullslast(),
            story_data.Story.pulse_score.desc().nullslast(),
            story_data.Story.created_at.desc(),
        )
    else:
        query = query.order_by(story_data.Story.created_at.desc())

    rows = query.limit(limit).all()

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
    for s, avg_rating in rows:
        s_type = s.story_type.value if s.story_type else "confession"

        # Public identity only — never fall back to email on listing cards.
        author_display = (s.first_name or "").strip() or None
        if author_display and "@" in author_display:
            author_display = None

        feed_rating = round(float(avg_rating), 1) if avg_rating is not None else None

        excerpt = story_card_excerpt(s)

        items.append(StoryFeedItem(
            id=str(s.id),
            title=s.title or STORY_UNTITLED,
            excerpt=excerpt,
            description=excerpt,
            story_type=s_type,
            cover_image_url=format_media_url(s.cover_image_url or fallback_images.get(s_type)),
            audio_path=format_media_url(s.audio_path),
            rating=feed_rating,
            listened_count=s.views_count or 0,
            author_name=author_display,
            location=s.location,
            gender=s.gender,
            sexual_orientation=s.sexual_orientation,
            occupation=s.occupation,
            age=s.age,
            audio_duration_seconds=s.audio_duration_seconds,
            is_explicit=bool(s.high_intensity),
            tags=_as_str_list(s.tags)[:8],
            growth_areas=_as_str_list(s.growth_areas)[:4],
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

    # Regular users can only see approved stories the author has not withdrawn
    if (
        story.moderation_status != ModerationStatus.approved
        or story.submission_status == SubmissionStatus.withdrawn
    ):
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

    # --- Resolve cover: per-story artwork first, then admin category fallback ---
    from app.data import cover_image as cover_data
    from app.model.cover_image import CoverImageType
    s_type = story.story_type.value if story.story_type else "confession"
    cover_image_url = story.cover_image_url
    if not cover_image_url:
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
        location=story.location,
        gender=story.gender,
        sexual_orientation=story.sexual_orientation,
        occupation=story.occupation,
        age=story.age,
        hero_hook=story.hero_hook,
        hero_tagline=story.hero_tagline,
        voice_name=story.voice_name,
        track_id=story.track_id,
        high_intensity=story.high_intensity,
        is_explicit=bool(story.high_intensity),
        listened_count=story.views_count or 0,
        audio_duration_seconds=story.audio_duration_seconds,
        alignment=story.alignment,
        created_at=story.created_at.isoformat(),
        avg_rating=avg_rating,
        avg_resonance=avg_resonance,
        total_reflections=total_reflections,
        tags=_as_str_list(story.tags)[:8],
        top_tags=top_tags,
    )
    return success_response("Story details fetched", status.HTTP_200_OK, result)
