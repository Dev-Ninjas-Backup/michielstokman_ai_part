from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_or_create_wallet, reset_wallet_if_needed
from app.core.database import get_db
from app.models.entities import Story, StoryReflection, User
from app.schemas.dto import (
    ReflectionCreateRequest,
    ReflectionResponse,
    StoryGenerateRequest,
    StoryItemResponse,
    StoryJobResponse,
    StoryStatusResponse,
)
from app.services.story_service import process_story_now, queue_story


router = APIRouter(prefix="/stories", tags=["Stories"])


def _complete_story_background(story_id: str):
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if story:
            process_story_now(db, story)
    finally:
        db.close()


@router.post("/generate", response_model=StoryJobResponse)
def generate_story(
    payload: StoryGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wallet = reset_wallet_if_needed(db, get_or_create_wallet(db, current_user.id))
    if wallet.remaining <= 0:
        raise HTTPException(status_code=402, detail="NO_CREDITS")

    wallet.remaining -= 1
    db.commit()

    story = queue_story(db, current_user.id, payload.content_type, payload.model_dump())
    background_tasks.add_task(_complete_story_background, story.id)

    return StoryJobResponse(
        story_id=story.id,
        job_id=story.job_id,
        status="processing",
        message="Story queued",
    )


@router.get("/jobs/{job_id}", response_model=StoryStatusResponse)
def get_story_job(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    story = db.query(Story).filter(Story.job_id == job_id, Story.user_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Job not found")
    return StoryStatusResponse(
        story_id=story.id,
        job_id=story.job_id,
        status=story.status.value,
        story_text=story.story_text,
        audio_path=story.audio_path,
    )


@router.get("/me", response_model=list[StoryItemResponse])
def my_stories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    stories = (
        db.query(Story)
        .filter(Story.user_id == current_user.id)
        .order_by(Story.created_at.desc())
        .limit(50)
        .all()
    )
    return [StoryItemResponse.model_validate(item, from_attributes=True) for item in stories]


@router.get("/{story_id}", response_model=StoryItemResponse)
def get_story(story_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    story = db.query(Story).filter(Story.id == story_id, Story.user_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return StoryItemResponse.model_validate(story, from_attributes=True)


@router.post("/{story_id}/reflection", response_model=ReflectionResponse)
def submit_reflection(
    story_id: str,
    payload: ReflectionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story = db.query(Story).filter(Story.id == story_id, Story.user_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    reflection = db.query(StoryReflection).filter(StoryReflection.story_id == story_id).first()
    if reflection:
        reflection.resonance_score = payload.resonance_score
        reflection.moment_tags = payload.moment_tags
        reflection.thought_note = payload.thought_note
        reflection.reaction = payload.reaction
    else:
        reflection = StoryReflection(
            story_id=story_id,
            user_id=current_user.id,
            resonance_score=payload.resonance_score,
            moment_tags=payload.moment_tags,
            thought_note=payload.thought_note,
            reaction=payload.reaction,
        )
        db.add(reflection)

    db.commit()
    db.refresh(reflection)
    return ReflectionResponse.model_validate(reflection, from_attributes=True)


@router.get("/{story_id}/reflection", response_model=ReflectionResponse)
def get_reflection(story_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reflection = (
        db.query(StoryReflection)
        .join(Story, Story.id == StoryReflection.story_id)
        .filter(StoryReflection.story_id == story_id, Story.user_id == current_user.id)
        .first()
    )
    if not reflection:
        raise HTTPException(status_code=404, detail="Reflection not found")
    return ReflectionResponse.model_validate(reflection, from_attributes=True)
