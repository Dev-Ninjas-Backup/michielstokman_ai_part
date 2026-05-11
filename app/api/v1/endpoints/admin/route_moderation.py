from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
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

@router.get("/admin/moderation/queue", response_model=ApiResponse[ModerationQueueResponse])
def get_moderation_queue(
    moderation_status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """
    Fetch list of stories for moderation queue, with optional status filter and search.
    Only accessible to admin users.
    """
    stories = story_data.get_moderation_stories(
        db, 
        limit=limit, 
        offset=offset, 
        status_filter=moderation_status, 
        search=search
    )
    
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
                cover_image_url=story.cover_image_url,
            )
        )
    
    # Clean stats keys (e.g. from 'ModerationStatus.pending' to 'pending')
    clean_stats = {str(k).replace("ModerationStatus.", ""): v for k, v in stats.items()}
    
    # Get total matching the current filter + search combination for pagination
    # total_pages/total_items logic can be kept in some other field if needed, but Figma 
    # needs an "all" count which is the sum of all statuses.
    all_count = sum(clean_stats.values())
    
    result = ModerationQueueResponse(
        stories=story_items,
        all=all_count,
        pending=clean_stats.get("pending", 0),
        flagged=clean_stats.get("flagged", 0),
        approved=clean_stats.get("approved", 0),
        rejected=clean_stats.get("rejected", 0),
    )
    return success_response("Moderation queue fetched", status.HTTP_200_OK, result)


@router.get("/admin/moderation/story/{story_id}", response_model=ApiResponse[StoryDetailResponse])
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
    
    result = StoryDetailResponse(
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
    return success_response("Story details fetched", status.HTTP_200_OK, result)


@router.put("/admin/moderation/story/{story_id}", response_model=ApiResponse[StoryDetailResponse])
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
    
    result = StoryDetailResponse(
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
    return success_response("Story updated successfully", status.HTTP_200_OK, result)


@router.post("/admin/moderation/story/{story_id}/approve", response_model=ApiResponse[ApproveStoryResponse])
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
    
    result = ApproveStoryResponse(
        message="Story approved successfully",
        story_id=story.id,
        status=str(story.moderation_status).replace("ModerationStatus.", ""),
    )
    return success_response("Story approved successfully", status.HTTP_200_OK, result)


@router.post("/admin/moderation/story/{story_id}/reject", response_model=ApiResponse[RejectStoryResponse])
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
    
    result = RejectStoryResponse(
        message="Story rejected",
        story_id=story.id,
        status=str(story.moderation_status).replace("ModerationStatus.", ""),
    )
    return success_response("Story rejected", status.HTTP_200_OK, result)


@router.delete("/admin/moderation/story/{story_id}", response_model=ApiResponse[DeleteStoryResponse])
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
    
    result = DeleteStoryResponse(
        message="Story deleted successfully",
        story_id=story_id_to_return,
    )
    return success_response("Story deleted successfully", status.HTTP_200_OK, result)
