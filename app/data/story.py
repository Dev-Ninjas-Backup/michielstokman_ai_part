"""
app/data/story.py
Raw database queries for the Story table.
No business logic here — only DB read/write operations.
"""
import uuid
import random
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
    Seeds with social proof metrics rather than starting at 0.
    """
    views = random.randint(150, 450)
    reflections = random.randint(50, 150)
    shares = random.randint(20, 80)
    pulse = round(random.uniform(88.0, 97.5), 1)

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
        views_count=views,
        shares_count=shares,
        reflections_count=reflections,
        pulse_score=pulse,
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
    alignment: Optional[list] = None,
) -> Story:
    """Updates a Story row with the generated text + audio and marks it completed."""
    # The LLM omits the TITLE: marker often enough that overwriting
    # unconditionally would erase the title the member submitted.
    if title:
        story.title = title
    story.story_text = story_text
    story.audio_path = audio_path
    story.generation_status = GenerationStatus.completed
    if audio_duration_seconds is not None:
        story.audio_duration_seconds = audio_duration_seconds
    if alignment is not None:
        story.alignment = alignment
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

# ---------------------------------------------------------------------------
# Member-owned story management
# ---------------------------------------------------------------------------


def get_member_story(db: Session, story_id: str, user_id: str) -> Optional[Story]:
    """
    Fetches a story only if it belongs to the given member.
    Returns None for someone else's story so callers can 404 rather than 403,
    which avoids confirming that the id exists.
    """
    try:
        story_uuid = uuid.UUID(story_id)
    except (ValueError, AttributeError, TypeError):
        return None
    return (
        db.query(Story)
        .filter(Story.id == story_uuid, Story.user_id == uuid.UUID(user_id))
        .first()
    )


def _member_story_query(
    db: Session,
    user_id: str,
    story_type: Optional[str] = None,
    submission_status: Optional[str] = None,
    generation_status: Optional[str] = None,
):
    from app.model.story import SubmissionStatus

    query = db.query(Story).filter(Story.user_id == uuid.UUID(user_id))

    if story_type and story_type.lower() != "all":
        query = query.filter(Story.story_type == StoryType(story_type.lower()))
    if submission_status and submission_status.lower() != "all":
        query = query.filter(Story.submission_status == SubmissionStatus(submission_status.lower()))
    if generation_status and generation_status.lower() != "all":
        query = query.filter(Story.generation_status == GenerationStatus(generation_status.lower()))

    return query


def list_member_stories(
    db: Session,
    user_id: str,
    story_type: Optional[str] = None,
    submission_status: Optional[str] = None,
    generation_status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Story]:
    """Returns a member's own stories, newest first, regardless of moderation state."""
    return (
        _member_story_query(db, user_id, story_type, submission_status, generation_status)
        .order_by(Story.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_member_stories(
    db: Session,
    user_id: str,
    story_type: Optional[str] = None,
    submission_status: Optional[str] = None,
    generation_status: Optional[str] = None,
) -> int:
    return _member_story_query(
        db, user_id, story_type, submission_status, generation_status
    ).count()


def withdraw_story(db: Session, story: Story) -> Story:
    """
    Withdraws a member's story from publication. The row is kept so the member
    retains their library and the story number is never reused.
    """
    from datetime import datetime, timezone
    from app.model.story import SubmissionStatus

    story.submission_status = SubmissionStatus.withdrawn
    story.withdrawn_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(story)
    return story


def resubmit_story(db: Session, story: Story) -> Story:
    """
    Puts a withdrawn story back into the publication pipeline. Moderation is
    reset to pending so an admin re-reviews it before it reaches the feed again.
    """
    from app.model.story import ModerationStatus, SubmissionStatus

    story.submission_status = SubmissionStatus.submitted
    story.withdrawn_at = None
    story.moderation_status = ModerationStatus.pending
    story.moderation_notes = None
    story.moderation_reviewed_by = None
    story.moderation_reviewed_at = None
    db.commit()
    db.refresh(story)
    return story


def start_regeneration(db: Session, story: Story, job_id: str) -> Story:
    """
    Marks a story as being re-processed through the AI pipeline after an edit.
    Moderation returns to pending because the content is about to change.
    """
    from app.model.story import ModerationStatus

    story.job_id = job_id
    story.generation_status = GenerationStatus.processing
    story.moderation_status = ModerationStatus.pending
    story.moderation_notes = None
    story.moderation_reviewed_by = None
    story.moderation_reviewed_at = None
    story.regeneration_count = (story.regeneration_count or 0) + 1
    db.commit()
    db.refresh(story)
    return story


def set_story_audio(
    db: Session,
    story: Story,
    audio_path: str,
    voice_name: Optional[str],
    voice_id: Optional[str],
    uses_custom_voice: bool,
    audio_duration_seconds: Optional[int] = None,
    alignment: Optional[list] = None,
) -> Story:
    """Replaces the narration on an existing story (used when re-narrating)."""
    story.audio_path = audio_path
    story.voice_name = voice_name
    story.voice_id = voice_id
    story.uses_custom_voice = uses_custom_voice
    if audio_duration_seconds is not None:
        story.audio_duration_seconds = audio_duration_seconds
    if alignment is not None:
        story.alignment = alignment
    story.generation_status = GenerationStatus.completed
    db.commit()
    db.refresh(story)
    return story


def set_story_cover(
    db: Session,
    story: Story,
    image_url: Optional[str],
    image_key: Optional[str],
    source,
) -> Story:
    """Points a story at a new cover image and records where it came from."""
    story.cover_image_url = image_url
    story.cover_image_key = image_key
    story.image_source = source
    db.commit()
    db.refresh(story)
    return story


def set_social_intros(db: Session, story: Story, intros: dict) -> Story:
    """Stores the generated Meta/Spotify introduction copy."""
    from datetime import datetime, timezone

    story.social_intros = intros
    story.social_intros_generated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(story)
    return story


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
    from app.model.story import ModerationStatus, SubmissionStatus
    from app.model.user import User
    
    query = db.query(Story).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.submission_status != SubmissionStatus.withdrawn,
    )
    
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
    from app.model.story import ModerationStatus, SubmissionStatus
    from app.model.user import User
    
    query = db.query(Story).filter(
        Story.generation_status == GenerationStatus.completed,
        Story.submission_status != SubmissionStatus.withdrawn,
    )
    
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
    """Permanently delete a story and its associated audio file from S3 or local disk."""
    import logging
    import os
    logger = logging.getLogger(__name__)

    audio_path: str | None = story.audio_path

    # ── 1. Delete the DB row first so the story is gone even if file cleanup fails ──
    db.delete(story)
    db.commit()

    # ── 2. Best-effort file cleanup ───────────────────────────────────────────────
    if not audio_path:
        return

    try:
        from app.core.config import settings

        # If the audio_path is a relative local path (media/audio/…), try S3 first,
        # then fall back to deleting from the local filesystem.
        if settings.AWS_BUCKET_NAME and settings.AWS_ACCESS_KEY_ID:
            import boto3
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION_NAME,
            )
            # Strip any leading slash so the key matches what was uploaded
            s3_key = audio_path.lstrip("/")
            s3.delete_object(Bucket=settings.AWS_BUCKET_NAME, Key=s3_key)
            logger.info(f"Deleted audio from S3: s3://{settings.AWS_BUCKET_NAME}/{s3_key}")
        else:
            # Local filesystem fallback — audio_path is relative to the working dir
            local_path = audio_path.lstrip("/")
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"Deleted local audio file: {local_path}")
    except Exception as exc:
        # Log but do NOT raise — story is already deleted from the DB
        logger.warning(f"Could not delete audio file '{audio_path}': {exc}")
