"""
app/data/feedback.py
Database operations for story feedback.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.model.feedback import StoryFeedback


def get_feedback_by_story_and_user(
    db: Session, story_id: str, user_id: str
) -> Optional[StoryFeedback]:
    """Check if a user has already submitted feedback for a story."""
    return (
        db.query(StoryFeedback)
        .filter(StoryFeedback.story_id == story_id, StoryFeedback.user_id == user_id)
        .first()
    )


def create_feedback(
    db: Session,
    story_id: str,
    user_id: str,
    touch_score: Optional[float] = None,
    star_rating: Optional[float] = None,
    resonance_tags: Optional[List[str]] = None,
    reaction: Optional[str] = None,
    feedback_text: Optional[str] = None,
) -> StoryFeedback:
    """Create a new feedback entry."""
    feedback = StoryFeedback(
        story_id=story_id,
        user_id=user_id,
        touch_score=touch_score,
        star_rating=star_rating,
        resonance_tags=resonance_tags,
        reaction=reaction,
        feedback_text=feedback_text,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def update_feedback(
    db: Session,
    feedback: StoryFeedback,
    touch_score: Optional[float] = None,
    star_rating: Optional[float] = None,
    resonance_tags: Optional[List[str]] = None,
    reaction: Optional[str] = None,
    feedback_text: Optional[str] = None,
) -> StoryFeedback:
    """Update an existing feedback entry (user re-submits)."""
    if touch_score is not None:
        feedback.touch_score = touch_score
    if star_rating is not None:
        feedback.star_rating = star_rating
    if resonance_tags is not None:
        feedback.resonance_tags = resonance_tags
    if reaction is not None:
        feedback.reaction = reaction
    if feedback_text is not None:
        feedback.feedback_text = feedback_text
    db.commit()
    db.refresh(feedback)
    return feedback
