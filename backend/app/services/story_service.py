import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import Story, StoryStatus


def generate_story_text(content_type: str, context: dict) -> str:
    life_phase = context.get("life_phase") or "this phase of your life"
    trigger = context.get("specific_trigger") or "what has been heavy lately"
    high_intensity = "with direct, brave language" if context.get("high_intensity") else "with gentle grounding"

    opening = {
        "confession": "You do not need to perform strength right now.",
        "meditation": "Take one breath that belongs only to you.",
        "journey": "Today is one honest step toward your liberation.",
    }.get(content_type, "Begin where you are.")

    return (
        f"{opening}\n\n"
        f"In {life_phase}, this reflection meets {trigger}, {high_intensity}. "
        "Name one truth, release one burden, and choose one next action before the day ends."
    )


def queue_story(db: Session, user_id: str, content_type: str, payload: dict) -> Story:
    story = Story(
        id=str(uuid.uuid4()),
        job_id=str(uuid.uuid4()),
        user_id=user_id,
        content_type=content_type,
        track_id=payload.get("track_id"),
        prompt_context=payload,
        status=StoryStatus.processing,
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def process_story_now(db: Session, story: Story) -> Story:
    context = story.prompt_context or {}
    story.story_text = generate_story_text(story.content_type.value, context)
    story.audio_path = None
    story.status = StoryStatus.completed
    story.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(story)
    return story
