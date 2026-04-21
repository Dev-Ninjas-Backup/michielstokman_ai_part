"""
app/data/admin_chat.py

Raw database queries for the Admin Metrics Chat feature.
No business logic here — only DB read operations.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.model.story import Story, GenerationStatus, ModerationStatus
from app.model.feedback import StoryFeedback
from app.model.liberation import UserJourney, UserJourneyStep, StepStatus


def get_top_resonance_stories(db: Session, days: int = 7, limit: int = 5) -> list[dict]:
    """
    Returns stories with the highest average touch_score from feedback,
    filtered to the last `days` days. Includes reflection count and title.
    Pulse score is derived as avg(touch_score) — stored nowhere, computed here.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    results = (
        db.query(
            Story.id,
            Story.title,
            Story.story_type,
            func.avg(StoryFeedback.touch_score).label("avg_pulse"),
            func.count(StoryFeedback.id).label("reflection_count"),
        )
        .join(StoryFeedback, StoryFeedback.story_id == Story.id)
        .filter(
            Story.generation_status == GenerationStatus.completed,
            Story.created_at >= since,
            StoryFeedback.touch_score.isnot(None),
        )
        .group_by(Story.id, Story.title, Story.story_type)
        .order_by(func.avg(StoryFeedback.touch_score).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "title": r.title or "Untitled",
            "story_type": str(r.story_type),
            "avg_pulse": round(float(r.avg_pulse), 1),
            "reflection_count": r.reflection_count,
        }
        for r in results
    ]


def get_growth_area_averages(db: Session) -> list[dict]:
    """
    Returns average touch_score grouped by life_phase (growth area).
    Only includes life_phases with at least 3 feedback entries for
    statistical relevance.
    """
    results = (
        db.query(
            Story.life_phase,
            func.avg(StoryFeedback.touch_score).label("avg_score"),
            func.count(StoryFeedback.id).label("count"),
        )
        .join(StoryFeedback, StoryFeedback.story_id == Story.id)
        .filter(
            Story.life_phase.isnot(None),
            StoryFeedback.touch_score.isnot(None),
        )
        .group_by(Story.life_phase)
        .having(func.count(StoryFeedback.id) >= 3)
        .order_by(func.avg(StoryFeedback.touch_score).desc())
        .all()
    )
    return [
        {
            "growth_area": r.life_phase,
            "avg_score": round(float(r.avg_score), 1),
            "sample_count": r.count,
        }
        for r in results
    ]


def get_journey_completion_rates(db: Session) -> dict:
    """
    Returns journey counts by status and the overall step completion rate
    across all active user journeys.
    """
    journey_stats = (
        db.query(
            UserJourney.status,
            func.count(UserJourney.id).label("count"),
        )
        .group_by(UserJourney.status)
        .all()
    )
    journey_counts = {str(row.status): row.count for row in journey_stats}

    total_steps = db.query(func.count(UserJourneyStep.id)).scalar() or 0
    completed_steps = (
        db.query(func.count(UserJourneyStep.id))
        .filter(UserJourneyStep.status == StepStatus.completed)
        .scalar()
        or 0
    )
    step_completion_rate = (
        round((completed_steps / total_steps) * 100, 1) if total_steps > 0 else 0.0
    )

    return {
        "journeys_by_status": journey_counts,
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "step_completion_rate_pct": step_completion_rate,
    }


def get_pending_moderation_count(db: Session) -> int:
    """Returns the count of completed stories awaiting moderation review."""
    return (
        db.query(func.count(Story.id))
        .filter(
            Story.moderation_status == ModerationStatus.pending,
            Story.generation_status == GenerationStatus.completed,
        )
        .scalar()
        or 0
    )


def get_platform_overview(db: Session) -> dict:
    """
    Returns a high-level platform snapshot: total completed stories,
    average touch score, average star rating, and total feedback entries.
    """
    total_stories = (
        db.query(func.count(Story.id))
        .filter(Story.generation_status == GenerationStatus.completed)
        .scalar()
        or 0
    )
    agg = db.query(
        func.avg(StoryFeedback.touch_score).label("avg_touch"),
        func.avg(StoryFeedback.star_rating).label("avg_star"),
        func.count(StoryFeedback.id).label("total_feedback"),
    ).one()

    return {
        "total_completed_stories": total_stories,
        "avg_touch_score": round(float(agg.avg_touch), 2) if agg.avg_touch else None,
        "avg_star_rating": round(float(agg.avg_star), 2) if agg.avg_star else None,
        "total_feedback_entries": agg.total_feedback or 0,
    }
