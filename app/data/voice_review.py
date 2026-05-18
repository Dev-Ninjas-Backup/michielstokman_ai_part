"""
app/data/voice_review.py
Database queries for the Voice Review Admin Dashboard.
"""
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, String, func

from app.model.story import Story, GenerationStatus, StoryType


def get_voice_review_stories(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    story_type_filter: Optional[str] = None
) -> Tuple[List[Story], int]:
    """
    Fetches stories that have completed generation and have an audio_path.
    Returns a tuple of (stories_list, total_count).
    """
    query = db.query(Story).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.audio_path.isnot(None),
        Story.story_type.in_([StoryType.confession, StoryType.meditation])
    )

    if story_type_filter:
        val = story_type_filter.lower()
        if val != "all":
            if val in ("story", "stories", "confession", "confessions"):
                query = query.filter(Story.story_type == StoryType.confession)
            elif val in ("meditation", "meditations"):
                query = query.filter(Story.story_type == StoryType.meditation)

    if search:
        search_term = f"%{search}%"
        
        # If searching for "Story", also search for "confession"
        # If searching for "Meditations", also search for "meditation"
        extra_filters = []
        if "story" in search.lower():
            extra_filters.append(Story.story_type == StoryType.confession)
        if "meditation" in search.lower():
            extra_filters.append(Story.story_type == StoryType.meditation)

        query = query.filter(
            or_(
                Story.title.ilike(search_term),
                Story.story_type.cast(String).ilike(search_term),
                *extra_filters
            )
        )

    total = query.count()
    stories = query.order_by(desc(Story.created_at)).offset(offset).limit(limit).all()

    return stories, total


def get_voice_review_stats(db: Session) -> dict:
    """
    Returns a dictionary of counts for voice review stories grouped by story_type.
    """
    results = db.query(
        Story.story_type,
        func.count(Story.id)
    ).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.audio_path.isnot(None),
        Story.story_type.in_([StoryType.confession, StoryType.meditation])
    ).group_by(Story.story_type).all()

    counts = {
        "confession": 0,
        "meditation": 0
    }
    for stype, count in results:
        val = str(stype).replace("StoryType.", "").lower()
        counts[val] = count

    return counts
