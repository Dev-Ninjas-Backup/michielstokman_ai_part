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
    track_id: Optional[str] = None,
    life_phase: Optional[str] = None,
    emotional_context: Optional[dict] = None,
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
        track_id=track_id,
        life_phase=life_phase,
        emotional_context=emotional_context,
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
    audio_path: Optional[str] = None,
) -> Story:
    """Updates a Story row with the generated text + audio and marks it completed."""
    story.story_text = story_text
    story.audio_path = audio_path
    story.generation_status = GenerationStatus.completed
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
