from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.model.user import User
from app.data import story as story_data
from app.schemas.schema_story import (
    StoryDetailResponse,
    StoryListItemResponse,
    ModerationQueueResponse,
    UpdateStoryRequest,
    ApproveStoryResponse,
    RejectStoryRequest,
    RejectStoryResponse,
    DeleteStoryResponse,
)

router = APIRouter()


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/admin/moderation/queue", response_model=ModerationQueueResponse)
def get_moderation_queue(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """
    Fetch list of pending stories awaiting moderation.
    Only accessible to admin users.
    """
    stories = story_data.get_pending_stories(db, limit=limit, offset=offset)
    
    story_items = []
    for story in stories:
        # Get author name from user relationship
        author_name = story.user.email if story.user else "Admin"
        story_items.append(
            StoryListItemResponse(
                id=story.id,
                title=story.title or "Untitled",
                story_type=str(story.story_type).replace("StoryType.", "").capitalize(),
                author=author_name,
                created_at=story.created_at.isoformat(),
                moderation_status=str(story.moderation_status).replace("ModerationStatus.", ""),
            )
        )
    
    # Get stats
    stats = story_data.get_moderation_stats(db)
    total = story_data.count_pending_stories(db)
    
    return ModerationQueueResponse(
        stories=story_items,
        total=total,
        pending=stats.get("pending", 0),
        approved=stats.get("approved", 0),
        rejected=stats.get("rejected", 0),
    )


@router.get("/admin/moderation/story/{story_id}", response_model=StoryDetailResponse)
def get_story_details(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Fetch full story details for review.
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    author_name = story.user.email if story.user else "Admin"
    
    return StoryDetailResponse(
        id=story.id,
        title=story.title or "Untitled",
        story_type=str(story.story_type).replace("StoryType.", "").capitalize(),
        story_text=story.story_text,
        audio_path=story.audio_path,
        author=author_name,
        created_at=story.created_at.isoformat(),
        moderation_status=str(story.moderation_status).replace("ModerationStatus.", ""),
        moderation_notes=story.moderation_notes,
        country_city=story.country_city,
        life_phase=story.life_phase,
        relationship_status=story.relationship_status,
        deepest_desire_fear=story.deepest_desire_fear,
        specific_trigger=story.specific_trigger,
        emotional_context=story.emotional_context,
    )


@router.put("/admin/moderation/story/{story_id}", response_model=StoryDetailResponse)
def update_story_details(
    story_id: str,
    update_data: UpdateStoryRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Update story details (title, type, content).
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Update the story
    story = story_data.update_story_details(
        db,
        story,
        title=update_data.title,
        story_type=update_data.story_type,
        story_text=update_data.story_text,
    )
    
    author_name = story.user.email if story.user else "Admin"
    
    return StoryDetailResponse(
        id=story.id,
        title=story.title or "Untitled",
        story_type=str(story.story_type).replace("StoryType.", "").capitalize(),
        story_text=story.story_text,
        audio_path=story.audio_path,
        author=author_name,
        created_at=story.created_at.isoformat(),
        moderation_status=str(story.moderation_status).replace("ModerationStatus.", ""),
        moderation_notes=story.moderation_notes,
        country_city=story.country_city,
        life_phase=story.life_phase,
        relationship_status=story.relationship_status,
        deepest_desire_fear=story.deepest_desire_fear,
        specific_trigger=story.specific_trigger,
        emotional_context=story.emotional_context,
    )


@router.post("/admin/moderation/story/{story_id}/approve", response_model=ApproveStoryResponse)
def approve_story(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Approve a story for publication.
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Approve the story
    story = story_data.approve_story(db, story, str(current_user.id))
    
    return ApproveStoryResponse(
        message="Story approved successfully",
        story_id=story.id,
        status=str(story.moderation_status).replace("ModerationStatus.", ""),
    )


@router.post("/admin/moderation/story/{story_id}/reject", response_model=RejectStoryResponse)
def reject_story(
    story_id: str,
    payload: RejectStoryRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Reject a story with optional reason/notes.
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Reject the story
    story = story_data.reject_story(
        db,
        story,
        str(current_user.id),
        notes=payload.reason,
    )
    
    return RejectStoryResponse(
        message="Story rejected",
        story_id=story.id,
        status=str(story.moderation_status).replace("ModerationStatus.", ""),
    )


@router.delete("/admin/moderation/story/{story_id}", response_model=DeleteStoryResponse)
def delete_story(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a story.
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    story_id_to_return = story.id
    
    # Delete the story
    story_data.delete_story(db, story)
    
    return DeleteStoryResponse(
        message="Story deleted successfully",
        story_id=story_id_to_return,
    )
