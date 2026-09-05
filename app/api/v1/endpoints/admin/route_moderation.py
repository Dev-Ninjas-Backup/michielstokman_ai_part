from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.data import story as story_data
from app.model.story import SubmissionMode
from app.schemas.schema_story import (
    StoryDetailResponse,
    StoryListItemResponse,
    ModerationQueueResponse,
    UpdateStoryRequest,
    ApproveStoryRequest,
    ApproveStoryResponse,
    RejectStoryRequest,
    RejectStoryResponse,
    DeleteStoryResponse,
    SuggestFieldRequest,
    SuggestFieldResponse,
    RequestChangesRequest,
    RequestChangesResponse,
)

router = APIRouter()


def _enum_value(value) -> Optional[str]:
    if value is None:
        return None
    return value.value if getattr(value, "value", None) else str(value)


def to_story_detail(story) -> StoryDetailResponse:
    author_name = None
    if story.first_name and "@" not in story.first_name:
        author_name = story.first_name.strip()
    return StoryDetailResponse(
        id=story.id,
        title=story.title or "Untitled",
        story_type=str(story.story_type).replace("StoryType.", "").capitalize(),
        story_text=story.story_text,
        audio_path=story.audio_path,
        author=author_name or "—",
        created_at=story.created_at.isoformat(),
        moderation_status=str(story.moderation_status).replace("ModerationStatus.", ""),
        moderation_notes=story.moderation_notes,
        first_name=story.first_name,
        location=story.location,
        gender=story.gender,
        sexual_orientation=story.sexual_orientation,
        occupation=story.occupation,
        age=story.age,
        background=story.background,
        personality=story.personality,
        lifestyle=story.lifestyle,
        situation=story.situation,
        submission_mode=_enum_value(getattr(story, "submission_mode", None)),
        hero_hook=story.hero_hook,
        hero_tagline=story.hero_tagline,
        editorial_brief=getattr(story, "editorial_brief", None),
        story_input=story.story_input,
        growth_areas=story.growth_areas,
        life_phase=story.life_phase,
        tags=story.tags,
        high_intensity=bool(getattr(story, "high_intensity", False)),
        voice_name=story.voice_name,
        voice_id=story.voice_id,
        cover_image_url=story.cover_image_url,
    )


def _require_story(db, story_id: str):
    story = story_data.get_story_by_id(db, story_id)
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found",
        )
    return story


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

            # Public identity only — never the login email.
            author_name = "—"
            if story.first_name and "@" not in story.first_name:
                author_name = story.first_name.strip()
            elif story.admin:
                author_name = "Admin"

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
    story = _require_story(db, story_id)
    return success_response(
        "Story details fetched",
        status.HTTP_200_OK,
        to_story_detail(story),
    )


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
    story = _require_story(db, story_id)

    voice_name = update_data.voice_name
    voice_id = None
    mode = _enum_value(getattr(story, "submission_mode", None))
    if voice_name and mode == SubmissionMode.human_ready.value:
        voice_name = None
    elif voice_name:
        from app.core.llm import ELEVENLABS_VOICES, canonical_voice_name
        canonical = canonical_voice_name(voice_name)
        if not canonical:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown catalog voice",
            )
        voice_name = canonical
        voice_id = ELEVENLABS_VOICES[canonical]

    story = story_data.update_story_details(
        db,
        story,
        title=update_data.title,
        story_type=update_data.story_type,
        story_text=update_data.story_text,
        hero_hook=update_data.hero_hook,
        hero_tagline=update_data.hero_tagline,
        first_name=update_data.first_name,
        location=update_data.location,
        gender=update_data.gender,
        sexual_orientation=update_data.sexual_orientation,
        occupation=update_data.occupation,
        age=update_data.age,
        tags=update_data.tags,
        growth_areas=update_data.growth_areas,
        life_phase=update_data.life_phase,
        high_intensity=update_data.high_intensity,
        editorial_brief=update_data.editorial_brief,
        voice_name=voice_name,
        voice_id=voice_id,
    )

    return success_response(
        "Story updated successfully",
        status.HTTP_200_OK,
        to_story_detail(story),
    )


@router.post("/admin/moderation/story/{story_id}/suggest", response_model=ApiResponse[SuggestFieldResponse])
def suggest_story_field(
    story_id: str,
    payload: SuggestFieldRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    AI draft for one editorial field. Does not write the story row.
    Admin Save (PUT) persists the chosen value.
    """
    from app.services.service_ai import AIService

    story = _require_story(db, story_id)
    mode = _enum_value(getattr(story, "submission_mode", None))
    story_type = _enum_value(story.story_type) or "confession"
    text = (story.story_text or story.story_input or "").strip()
    field = payload.field

    if field == "voice" and mode == SubmissionMode.human_ready.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fully narrated stories keep the uploaded recording.",
        )

    if field in ("hook", "tagline", "moods", "analysis") and not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This story has no text to suggest from.",
        )

    result = SuggestFieldResponse(field=field)

    if field == "hook":
        result.hero_hook = AIService.generate_hero_hook(
            text, story_type=story_type, title=story.title
        )
    elif field == "tagline":
        result.hero_tagline = AIService.generate_hero_tagline(
            text, story_type=story_type, title=story.title
        )
    elif field == "moods":
        moods = AIService.generate_moods(
            text, story_type=story_type, title=story.title
        ) or {}
        tags = moods.get("tags") or []
        growth = moods.get("growth_areas") or []
        life_phase = moods.get("life_phase")
        if not tags and not growth and not life_phase:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not generate moods. Try again.",
            )
        result.tags = tags
        result.growth_areas = growth
        result.life_phase = life_phase
    elif field == "analysis":
        result.editorial_brief = AIService.generate_editorial_brief(
            text,
            story_type=story_type,
            title=story.title,
            first_name=story.first_name,
            tags=story.tags,
        )
    elif field == "voice":
        name, voice_id, _custom = AIService.resolve_voice(
            gender=story.gender,
            text=text or story.title,
        )
        result.voice_name = name
        result.voice_id = voice_id

    return success_response("Suggestion generated", status.HTTP_200_OK, result)


@router.post(
    "/admin/moderation/story/{story_id}/request-changes",
    response_model=ApiResponse[RequestChangesResponse],
)
def request_story_changes(
    story_id: str,
    payload: RequestChangesRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Ask the member to revise. Stays pending — not on the public feed."""
    story = _require_story(db, story_id)
    story = story_data.request_story_changes(
        db, story, str(current_user.id), notes=payload.reason
    )
    result = RequestChangesResponse(
        message="Changes requested",
        story_id=story.id,
        status=str(story.moderation_status).replace("ModerationStatus.", ""),
    )
    return success_response("Changes requested", status.HTTP_200_OK, result)


@router.post("/admin/moderation/story/{story_id}/approve", response_model=ApiResponse[ApproveStoryResponse])
def approve_story(
    story_id: str,
    payload: Optional[ApproveStoryRequest] = Body(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Approve no longer publishes. Use POST /v1/admin/publications/{id}/publish.
    """
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Approving a story no longer publishes it. Approve content, cover, and voice in the publication workspace, then use Publish.",
    )


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
    story = _require_story(db, story_id)
    
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
    story = _require_story(db, story_id)
    
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
