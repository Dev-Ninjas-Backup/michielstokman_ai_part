"""
app/api/v1/endpoints/admin/route_voice_review.py
Admin endpoint for reviewing AI generated audio and requesting regeneration.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.data import voice_review as voice_data
from app.data import story as story_data
from app.services.service_ai import AIService
from app.schemas.schema_voice_review import (
    VoiceReviewItem,
    VoiceReviewResponse,
    VoiceRegenerateResponse
)

router = APIRouter()


import math
from app.schemas.schema_system import PaginationMeta

@router.get("/admin/voice-review", response_model=ApiResponse[VoiceReviewResponse])
def get_voice_review_list(
    story_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    page: Optional[int] = None,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Fetch a list of stories that have audio generated for Voice Review.
    Allows searching by title or type, and filtering by story_type.
    """
    if page is not None and page > 0:
        offset = (page - 1) * limit
    else:
        page = (offset // limit) + 1 if limit > 0 else 1

    stories, total = voice_data.get_voice_review_stories(
        db, limit=limit, offset=offset, search=search, story_type_filter=story_type
    )

    items = []
    for story in stories:
        duration_str = None
        if story.audio_duration_seconds:
            m, s = divmod(story.audio_duration_seconds, 60)
            duration_str = f"{m}:{s:02d}"

        # Map story_type to Figma display names
        display_type = str(story.story_type).replace("StoryType.", "").capitalize()
        if display_type == "Confession":
            display_type = "Story"
        elif display_type == "Meditation":
            display_type = "Meditations"
        elif display_type == "Transformation":
            display_type = "Journey"

        items.append(
            VoiceReviewItem(
                id=story.id,
                title=story.title or "Untitled",
                story_type=display_type,
                voice_name=story.voice_name,
                audio_duration=duration_str,
                created_at=story.created_at.strftime("%d %b %y"),  # format to "12 Jan 26"
                audio_path=story.audio_path,
            )
        )

    # Get tab counts
    stats = voice_data.get_voice_review_stats(db)
    all_count = sum(stats.values())
    stories_count = stats.get("confession", 0)
    meditations_count = stats.get("meditation", 0)

    total_pages = math.ceil(total / limit) if limit > 0 else 1
    if total_pages == 0:
        total_pages = 1

    pagination_meta = PaginationMeta(
        total=total,
        page=page,
        limit=limit,
        totalPages=total_pages
    )

    result = VoiceReviewResponse(
        items=items,
        total=total,
        all=all_count,
        stories=stories_count,
        meditations=meditations_count,
        meta=pagination_meta
    )
    return success_response("Voice review list fetched", status.HTTP_200_OK, result)



@router.post("/admin/voice-review/{story_id}/regenerate", response_model=ApiResponse[VoiceRegenerateResponse])
def regenerate_voice(
    story_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Re-submits the existing story text to ElevenLabs to regenerate the audio.
    Sets the story to 'processing' and runs the regeneration in the background.
    """
    story = story_data.get_story_by_id(db, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if not story.story_text:
        raise HTTPException(status_code=400, detail="Story has no text to generate audio from.")

    import uuid
    new_job_id = str(uuid.uuid4())
    story.job_id = new_job_id
    db.commit()

    # Define a simple background task to regenerate audio and save it
    def regenerate_audio_bg(job_id_str: str, story_db_id: str, text: str):
        from app.core.db import SessionLocal
        from app.model.story import Story as StoryModel
        from app.core.llm import generate_voice_elevenlabs, save_audio
        import logging

        logger = logging.getLogger(__name__)
        bg_db = SessionLocal()
        try:
            story_row = bg_db.query(StoryModel).filter(StoryModel.id == story_db_id).first()
            if not story_row:
                return

            audio_bytes = generate_voice_elevenlabs(text=text)
            audio_path = save_audio(audio_bytes)

            story_data.complete_story(
                db=bg_db,
                story=story_row,
                story_text=text,
                title=story_row.title,
                audio_path=audio_path,
            )
            # Estimate duration approx 150 words per minute
            word_count = len(text.split())
            duration_secs = int((word_count / 150) * 60)
            
            story_row.audio_duration_seconds = duration_secs
            # Optionally update voice_name if we knew it, or leave as is
            bg_db.commit()

            logger.info(f"[Regenerate Job {job_id_str}] Completed. Audio saved: {audio_path}")
        except Exception as e:
            logger.error(f"[Regenerate Job {job_id_str}] FAILED: {e}", exc_info=True)
            # We explicitly DO NOT fail the story here.
            # It was already completed, so we just keep the old audio.
        finally:
            bg_db.close()

    background_tasks.add_task(regenerate_audio_bg, new_job_id, str(story.id), story.story_text)

    result = VoiceRegenerateResponse(
        message="Voice regeneration started in the background",
        story_id=story.id,
        job_id=new_job_id
    )
    return success_response("Regeneration triggered", status.HTTP_202_ACCEPTED, result)
