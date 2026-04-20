"""
routes_feedback.py
User-facing endpoints for submitting story feedback/reviews.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_user
from app.model.user import User
from app.model.story import Story
from app.schemas.schema_feedback import StoryFeedbackRequest, StoryFeedbackResponse
import app.data.feedback as feedback_data

router = APIRouter()


@router.post(
    "/stories/{story_id}/feedback",
    response_model=ApiResponse[StoryFeedbackResponse],
    status_code=status.HTTP_201_CREATED,
)
def submit_story_feedback(
    story_id: str,
    request: StoryFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit feedback for a story after the Resonance Reflection screen.

    Captures: touch_score, star_rating, resonance_tags, reaction, feedback_text.
    If the user has already submitted feedback for this story, it updates the existing entry.
    """
    # Verify the story exists
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found.",
        )

    # Check if feedback already exists (upsert behavior)
    existing = feedback_data.get_feedback_by_story_and_user(
        db, story_id=story_id, user_id=str(current_user.id)
    )

    if existing:
        # Update the existing feedback
        feedback = feedback_data.update_feedback(
            db=db,
            feedback=existing,
            touch_score=request.touch_score,
            star_rating=request.star_rating,
            resonance_tags=request.resonance_tags,
            reaction=request.reaction,
            feedback_text=request.feedback_text,
        )
        message = "Feedback updated successfully."
    else:
        # Create new feedback
        feedback = feedback_data.create_feedback(
            db=db,
            story_id=story_id,
            user_id=str(current_user.id),
            touch_score=request.touch_score,
            star_rating=request.star_rating,
            resonance_tags=request.resonance_tags,
            reaction=request.reaction,
            feedback_text=request.feedback_text,
        )
        message = "Feedback submitted successfully."

    result = StoryFeedbackResponse(
        id=str(feedback.id),
        story_id=str(feedback.story_id),
        user_id=str(feedback.user_id),
        touch_score=feedback.touch_score,
        star_rating=feedback.star_rating,
        resonance_tags=feedback.resonance_tags,
        reaction=feedback.reaction,
        feedback_text=feedback.feedback_text,
        message=message,
    )
    return success_response(message, status.HTTP_201_CREATED, result)
