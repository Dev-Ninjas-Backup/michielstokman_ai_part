"""
app/data/story.py
Raw database queries for the Story table.
No business logic here — only DB read/write operations.
"""
import uuid
from typing import Optional
from sqlalchemy.orm import Session

from app.model.story import Story, StoryType, GenerationStatus


def create_story(
    db: Session,
    story_type: StoryType,
    job_id: str,
    user_id: Optional[str] = None,
    admin_id: Optional[str] = None,
    title: Optional[str] = None,
    first_name: Optional[str] = None,
    story_input: Optional[str] = None,
    growth_areas: Optional[list] = None,
    life_phase: Optional[str] = None,
    tags: Optional[list] = None,
    high_intensity: bool = False,
) -> Story:
    """
    Inserts a new Story row in 'processing' state.
    Exactly one of user_id or admin_id should be provided.
    """
    story = Story(
        story_type=story_type,
        job_id=job_id,
        generation_status=GenerationStatus.processing,
        user_id=uuid.UUID(user_id) if user_id else None,
        admin_id=uuid.UUID(admin_id) if admin_id else None,
        title=title,
        first_name=first_name,
        story_input=story_input,
        growth_areas=growth_areas,
        life_phase=life_phase,
        tags=tags,
        high_intensity=high_intensity,
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def complete_story(
    db: Session,
    story: Story,
    story_text: str,
    title: Optional[str] = None,
    audio_path: Optional[str] = None,
    audio_duration_seconds: Optional[int] = None,
) -> Story:
    """Updates a Story row with the generated text + audio and marks it completed."""
    story.title = title
    story.story_text = story_text
    story.audio_path = audio_path
    story.generation_status = GenerationStatus.completed
    if audio_duration_seconds is not None:
        story.audio_duration_seconds = audio_duration_seconds
    db.commit()
    db.refresh(story)
    return story


def fail_story(db: Session, story: Story) -> Story:
    """Marks a Story row as failed."""
    story.generation_status = GenerationStatus.failed
    db.commit()
    db.refresh(story)
    return story


def get_story_by_job_id(db: Session, job_id: str) -> Optional[Story]:
    """Fetches a Story by its async job_id."""
    return db.query(Story).filter(Story.job_id == job_id).first()


def get_story_by_id(db: Session, story_id: str) -> Optional[Story]:
    """Fetches a Story by its UUID primary key."""
    return db.query(Story).filter(Story.id == uuid.UUID(story_id)).first()


def get_stories_for_user(db: Session, user_id: str, limit: int = 20) -> list[Story]:
    """Returns the most recent stories for a given user, newest first."""
    return (
        db.query(Story)
        .filter(Story.user_id == uuid.UUID(user_id))
        .order_by(Story.created_at.desc())
        .limit(limit)
        .all()
    )

def count_stories_today(db: Session) -> int:
    """Get count of completed stories generated today."""
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(Story).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.created_at >= today_start
    ).count()

def count_failed_stories_today(db: Session) -> int:
    """Get count of failed stories today."""
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(Story).filter(
        Story.generation_status == GenerationStatus.failed,
        Story.created_at >= today_start
    ).count()

def get_stories_by_type_today(db: Session) -> dict:
    """Get breakdown of completed stories by type generated today."""
    from datetime import datetime, timezone
    from sqlalchemy import func
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    results = db.query(
        Story.story_type,
        func.count(Story.id).label("count")
    ).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.created_at >= today_start
    ).group_by(Story.story_type).all()
    return {str(story_type): count for story_type, count in results}

# Moderation functions

def get_moderation_stories(db: Session, limit: int = 20, offset: int = 0, status_filter: Optional[str] = None, search: Optional[str] = None) -> list[Story]:
    """Get all stories for moderation, optionally filtered by status and search."""
    from app.model.story import ModerationStatus
    from app.model.user import User
    
    query = db.query(Story).filter(Story.generation_status == GenerationStatus.completed)
    
    if status_filter and status_filter.lower() != 'all':
        query = query.filter(Story.moderation_status == ModerationStatus(status_filter.lower()))
        
    if search:
        search_term = f"%{search}%"
        query = query.outerjoin(User, Story.user_id == User.id).filter(
            (Story.title.ilike(search_term)) | 
            (User.email.ilike(search_term))
        )
        
    return query.order_by(Story.created_at.desc()).offset(offset).limit(limit).all()


def count_moderation_stories(db: Session, status_filter: Optional[str] = None, search: Optional[str] = None) -> int:
    """Count stories for moderation, optionally filtered by status and search."""
    from app.model.story import ModerationStatus
    from app.model.user import User
    
    query = db.query(Story).filter(Story.generation_status == GenerationStatus.completed)
    
    if status_filter and status_filter.lower() != 'all':
        query = query.filter(Story.moderation_status == ModerationStatus(status_filter.lower()))
        
    if search:
        search_term = f"%{search}%"
        query = query.outerjoin(User, Story.user_id == User.id).filter(
            (Story.title.ilike(search_term)) | 
            (User.email.ilike(search_term))
        )
        
    return query.count()

def get_moderation_stats(db: Session) -> dict:
    """Get counts of stories by moderation status."""
    from app.model.story import ModerationStatus
    from sqlalchemy import func
    stats = db.query(
        Story.moderation_status,
        func.count(Story.id).label("count")
    ).filter(
        Story.generation_status == GenerationStatus.completed
    ).group_by(Story.moderation_status).all()
    return {str(status): count for status, count in stats}

def approve_story(db: Session, story: Story, reviewed_by_id: str) -> Story:
    """Mark story as approved."""
    from app.model.story import ModerationStatus
    from datetime import datetime, timezone
    story.moderation_status = ModerationStatus.approved
    story.moderation_reviewed_by = uuid.UUID(reviewed_by_id)
    story.moderation_reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(story)
    return story

def reject_story(db: Session, story: Story, reviewed_by_id: str, notes: Optional[str] = None) -> Story:
    """Mark story as rejected with optional notes."""
    from app.model.story import ModerationStatus
    from datetime import datetime, timezone
    story.moderation_status = ModerationStatus.rejected
    story.moderation_reviewed_by = uuid.UUID(reviewed_by_id)
    story.moderation_reviewed_at = datetime.now(timezone.utc)
    story.moderation_notes = notes
    db.commit()
    db.refresh(story)
    return story

def update_story_details(db: Session, story: Story, title: Optional[str] = None, story_type: Optional[str] = None, story_text: Optional[str] = None) -> Story:
    """Update story details (title, type, content)."""
    if title is not None:
        story.title = title
    if story_type is not None:
        from app.model.story import StoryType
        story.story_type = StoryType(story_type)
    if story_text is not None:
        story.story_text = story_text
    db.commit()
    db.refresh(story)
    return story

def delete_story(db: Session, story: Story) -> None:
    """Permanently delete a story."""
    db.delete(story)
    db.commit()
