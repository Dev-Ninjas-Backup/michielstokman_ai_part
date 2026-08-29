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

import math
from app.schemas.schema_system import PaginationMeta

@router.get("/admin/moderation/queue", response_model=ApiResponse[ModerationQueueResponse])
def get_moderation_queue(
    moderation_status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
    page: Optional[int] = None,
):
    """
    Fetch list of stories for moderation queue, with optional status filter and search.
    Only accessible to admin users.
    """
    if page is not None and page > 0:
        offset = (page - 1) * limit
    else:
        page = (offset // limit) + 1 if limit > 0 else 1

    stories = story_data.get_moderation_stories(
        db, 
        limit=limit, 
        offset=offset, 
        status_filter=moderation_status, 
        search=search
    )
    
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        story_items = []
        for story in stories:
            # Map story_type to Figma display names
            display_type = str(story.story_type).replace("StoryType.", "").capitalize()
            if display_type == "Confession":
                display_type = "Confessions"
            elif display_type == "Meditation":
                display_type = "Meditations"
            elif display_type == "Transformation":
                display_type = "Journey"

            # Get author name safely
            author_name = "Admin"
            if story.user:
                author_name = story.user.email
            elif story.admin:
                author_name = story.admin.email

            story_items.append(
                StoryListItemResponse(
                    id=story.id,
                    title=story.title or "Untitled",
                    story_type=display_type,
                    author=author_name,
                    created_at=story.created_at.strftime("%d %b %y"),
                    moderation_status=str(story.moderation_status).replace("ModerationStatus.", "").capitalize(),
                    cover_image_url=story.cover_image_url,
                )
            )
        
        # Get stats for the tab counts
        stats = story_data.get_moderation_stats(db)
        
        # Clean stats keys (e.g. from 'ModerationStatus.pending' to 'pending')
        clean_stats = {str(k).replace("ModerationStatus.", ""): v for k, v in stats.items()}
        
        # Get total matching the current filter + search combination for pagination
        all_count = sum(clean_stats.values())
        
        # Count only the items matching the current filters for our pagination metadata
        total_filtered = story_data.count_moderation_stories(
            db,
            status_filter=moderation_status,
            search=search
        )

        total_pages = math.ceil(total_filtered / limit) if limit > 0 else 1
        if total_pages == 0:
            total_pages = 1

        pagination_meta = PaginationMeta(
            total=total_filtered,
            page=page,
            limit=limit,
            totalPages=total_pages
        )

        result = ModerationQueueResponse(
            stories=story_items,
            all=all_count,
            pending=clean_stats.get("pending", 0),
            flagged=clean_stats.get("flagged", 0),
            approved=clean_stats.get("approved", 0),
            rejected=clean_stats.get("rejected", 0),
            meta=pagination_meta,
        )
        return success_response("Moderation queue fetched", status.HTTP_200_OK, result)
    except Exception as e:
        logger.error(f"Moderation queue error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Moderation queue error: {str(e)}")



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
        first_name=story.first_name,
        location=story.location,
        gender=story.gender,
        occupation=story.occupation,
        age=story.age,
        hero_hook=story.hero_hook,
        story_input=story.story_input,
        growth_areas=story.growth_areas,
        life_phase=story.life_phase,
        tags=story.tags,
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
        first_name=story.first_name,
        location=story.location,
        gender=story.gender,
        occupation=story.occupation,
        age=story.age,
        hero_hook=story.hero_hook,
        story_input=story.story_input,
        growth_areas=story.growth_areas,
        life_phase=story.life_phase,
        tags=story.tags,
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


@router.delete("/admin/confession/{story_id}", response_model=ApiResponse[DeleteStoryResponse])
def delete_confession(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a confession story.
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Confession not found"
        )
        
    from app.model.story import StoryType
    if story.story_type != StoryType.confession:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Story is not a confession"
        )
    
    story_id_to_return = story.id
    
    # Delete the story
    story_data.delete_story(db, story)
    
    result = DeleteStoryResponse(
        message="Confession deleted successfully",
        story_id=story_id_to_return,
    )
    return success_response("Confession deleted successfully", status.HTTP_200_OK, result)


@router.delete("/admin/meditation/{story_id}", response_model=ApiResponse[DeleteStoryResponse])
def delete_meditation(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a meditation story.
    Only accessible to admin users.
    """
    story = story_data.get_story_by_id(db, story_id)
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meditation not found"
        )
        
    from app.model.story import StoryType
    if story.story_type != StoryType.meditation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Story is not a meditation"
        )
    
    story_id_to_return = story.id
    
    # Delete the story
    story_data.delete_story(db, story)
    
    result = DeleteStoryResponse(
        message="Meditation deleted successfully",
        story_id=story_id_to_return,
    )
    return success_response("Meditation deleted successfully", status.HTTP_200_OK, result)
