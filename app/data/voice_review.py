"""
app/data/voice_review.py
Database queries for the Voice Review Admin Dashboard.
"""
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, String

from app.model.story import Story, GenerationStatus


def get_voice_review_stories(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None
) -> Tuple[List[Story], int]:
    """
    Fetches stories that have completed generation and have an audio_path.
    Returns a tuple of (stories_list, total_count).
    """
    query = db.query(Story).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.audio_path.isnot(None)
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Story.title.ilike(search_term),
                Story.story_type.cast(String).ilike(search_term)
            )
        )

    total = query.count()
    stories = query.order_by(desc(Story.created_at)).offset(offset).limit(limit).all()

    return stories, total
