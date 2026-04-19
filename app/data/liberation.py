"""
app/data/liberation.py

Data-access layer for the Liberation Journey tables.
Pure DB operations — no business logic or HTTP concerns.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.model.liberation import (
    JourneyStatus,
    StepStatus,
    UserJourney,
    UserJourneyStep,
    JOURNEY_DAY_THEMES,
)


# ── Journey CRUD ────────────────────────────────────────────────────────────

def get_active_journey(db: Session, user_id: UUID, journey_code: Optional[str] = None) -> Optional[UserJourney]:
    """Return the user's active journey. If journey_code is provided, filters by it."""
    query = db.query(UserJourney).filter(
        UserJourney.user_id == user_id,
        UserJourney.status == JourneyStatus.active,
    )
    if journey_code:
        query = query.filter(UserJourney.journey_code == journey_code)
    return query.first()


def get_journey_by_id(db: Session, journey_id: UUID) -> Optional[UserJourney]:
    return db.query(UserJourney).filter(UserJourney.id == journey_id).first()


def get_any_journey_for_user(db: Session, user_id: UUID, journey_code: Optional[str] = None) -> Optional[UserJourney]:
    """Return the user's most recent journey. If journey_code is provided, filters by it."""
    query = db.query(UserJourney).filter(UserJourney.user_id == user_id)
    if journey_code:
        query = query.filter(UserJourney.journey_code == journey_code)
    return query.order_by(UserJourney.created_at.desc()).first()


def create_journey(
    db: Session,
    user_id: UUID,
    journey_code: str,
    total_days: int,
    reminder_preference: Optional[str] = None,
    definition_id: Optional[UUID] = None,
    day_themes: Optional[dict[int, str]] = None,
) -> UserJourney:
    """Create a new journey and pre-populate all step rows (Day 1 = available, rest = locked)."""
    journey = UserJourney(
        user_id=user_id,
        journey_code=journey_code,
        total_days=total_days,
        reminder_preference=reminder_preference,
        definition_id=definition_id,
        status=JourneyStatus.active,
    )
    db.add(journey)
    db.flush()  # get journey.id before creating steps

    themes = day_themes or JOURNEY_DAY_THEMES
    for day in range(1, total_days + 1):
        step = UserJourneyStep(
            journey_id=journey.id,
            day_number=day,
            day_theme=themes.get(day, f"Day {day}"),
            status=StepStatus.available if day == 1 else StepStatus.locked,
        )
        db.add(step)

    db.commit()
    db.refresh(journey)
    return journey


def mark_journey_completed(db: Session, journey: UserJourney) -> UserJourney:
    journey.status = JourneyStatus.completed
    db.commit()
    db.refresh(journey)
    return journey


# ── Step CRUD ───────────────────────────────────────────────────────────────

def get_step(db: Session, journey_id: UUID, day_number: int) -> Optional[UserJourneyStep]:
    return (
        db.query(UserJourneyStep)
        .filter(
            UserJourneyStep.journey_id == journey_id,
            UserJourneyStep.day_number == day_number,
        )
        .first()
    )


def save_morning_feeling(db: Session, step: UserJourneyStep, feeling: str) -> UserJourneyStep:
    step.morning_feeling = feeling
    db.commit()
    db.refresh(step)
    return step


def save_ai_content(
    db: Session,
    step: UserJourneyStep,
    greeting: str,
    exercise_text: str,
    why_text: str,
) -> UserJourneyStep:
    step.ai_greeting = greeting
    step.ai_exercise_text = exercise_text
    step.ai_why_text = why_text
    db.commit()
    db.refresh(step)
    return step


def complete_step(
    db: Session,
    step: UserJourneyStep,
    energy_level: int,
    opened: str,
    takeaway: str,
) -> UserJourneyStep:
    """Mark a step completed and save the user's post-exercise reflection."""
    step.energy_level_after = energy_level
    step.reflection_opened = opened
    step.reflection_takeaway = takeaway
    step.status = StepStatus.completed
    step.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(step)
    return step


def unlock_next_step(db: Session, journey_id: UUID, current_day: int) -> Optional[UserJourneyStep]:
    """Unlock the next day's step (if it exists)."""
    next_step = get_step(db, journey_id, current_day + 1)
    if next_step and next_step.status == StepStatus.locked:
        next_step.status = StepStatus.available
        db.commit()
        db.refresh(next_step)
    return next_step
