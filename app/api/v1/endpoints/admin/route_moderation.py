from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.data import story as story_data
from app.model.story import AssetReviewStatus, ImageSource, SubmissionMode
from app.schemas.schema_story import (
    AssetApprovalRequest,
    AssetStatusResponse,
    AuthorContact,
    StoryAudioReplaceResponse,
    StoryCoverRegenResponse,
    StoryCoverReplaceResponse,
    StoryDetailResponse,
    StoryListItemResponse,
    ModerationQueueResponse,
    PublishStoryResponse,
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
    VoiceRequirementRequest,
)

router = APIRouter()

ALLOWED_COVER_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_COVER_BYTES = 10 * 1024 * 1024

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
}
MAX_AUDIO_BYTES = 50 * 1024 * 1024


def _enum_value(value) -> Optional[str]:
    if value is None:
        return None
    return value.value if getattr(value, "value", None) else str(value)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _format_duration(seconds: Optional[int]) -> Optional[str]:
    if not seconds:
        return None
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def to_story_detail(story) -> StoryDetailResponse:
    author_name = story.user.email if story.user else "Admin"

    # Admin-only. The author's contact details must never reach a story card or
    # any public response.
    contact = None
    if story.user:
        profile = getattr(story.user, "profile", None)
        contact = AuthorContact(
            email=story.user.email,
            true_name=getattr(profile, "true_name", None),
        )

    return StoryDetailResponse(
        id=story.id,
        title=story.title or "Untitled",
        story_type=str(story.story_type).replace("StoryType.", "").capitalize(),
        story_text=story.story_text,
        audio_path=story.audio_path,
        audio_duration_seconds=story.audio_duration_seconds,
        author=author_name,
        created_at=story.created_at.isoformat(),
        submitted_at=_iso(story.created_at),
        updated_at=_iso(story.updated_at),
        moderation_status=str(story.moderation_status).replace("ModerationStatus.", ""),
        moderation_notes=story.moderation_notes,
        first_name=story.first_name,
        location=story.location,
        city=story.city,
        country=story.country,
        content_status=story_data.asset_status_value(story.content_status),
        cover_status=story_data.asset_status_value(story.cover_status),
        voice_status=story_data.asset_status_value(story.voice_status),
        voice_not_required=bool(story.voice_not_required),
        publication_status=story_data.publication_status(story),
        published_at=_iso(story.published_at),
        publish_blockers=story_data.publish_blockers(story),
        contact=contact,
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
    story_type: Optional[str] = None,
    missing: Optional[str] = None,
    publication_status: Optional[str] = None,
    sort: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
    page: Optional[int] = None,
):
    """
    Fetch list of stories for moderation queue.

    Filters: `moderation_status`, `search`, `story_type`, `publication_status`, and
    `missing` as a comma-separated list of `text`, `cover`, `voice`. Sort with
    `submitted_desc` (default), `submitted_asc`, `updated_desc` or `updated_asc`.
    Filtering runs in SQL so it spans the whole queue, not just the current page.
    """
    if page is not None and page > 0:
        offset = (page - 1) * limit
    else:
        page = (offset // limit) + 1 if limit > 0 else 1

    # The dashboard says "text" where the column is called content.
    missing_assets = [
        "content" if part.strip().lower() == "text" else part.strip().lower()
        for part in (missing or "").split(",")
        if part.strip()
    ]

    filters = dict(
        status_filter=moderation_status,
        search=search,
        story_type=story_type,
        missing=missing_assets,
        publication_status_filter=publication_status,
    )

    stories = story_data.get_moderation_stories(
        db,
        limit=limit,
        offset=offset,
        sort=sort,
        **filters,
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
                    first_name=story.first_name,
                    submitted_at=_iso(story.created_at),
                    updated_at=_iso(story.updated_at),
                    audio_path=story.audio_path,
                    audio_duration=_format_duration(story.audio_duration_seconds),
                    voice_name=story.voice_name,
                    high_intensity=bool(story.high_intensity),
                    has_text=bool((story.story_text or "").strip()),
                    content_status=story_data.asset_status_value(story.content_status),
                    cover_status=story_data.asset_status_value(story.cover_status),
                    voice_status=story_data.asset_status_value(story.voice_status),
                    voice_not_required=bool(story.voice_not_required),
                    publication_status=story_data.publication_status(story),
                    published_at=_iso(story.published_at),
                )
            )
        
        # Get stats for the tab counts
        stats = story_data.get_moderation_stats(db)
        
        # Clean stats keys (e.g. from 'ModerationStatus.pending' to 'pending')
        clean_stats = {str(k).replace("ModerationStatus.", ""): v for k, v in stats.items()}
        
        # Get total matching the current filter + search combination for pagination
        all_count = sum(clean_stats.values())
        
        # Count only the items matching the current filters for our pagination metadata
        total_filtered = story_data.count_moderation_stories(db, **filters)

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
        city=update_data.city,
        country=update_data.country,
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
        voice_not_required=update_data.voice_not_required,
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
    Approve a story for publication.
    Only accessible to admin users.
    """
    story = _require_story(db, story_id)

    # Approve the story
    story = story_data.approve_story(
        db,
        story,
        str(current_user.id),
        notes=payload.notes if payload else None,
    )
    
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


# ============================================================================
# Per-asset review + publish
#
# A publication is one record with three assets. Each can be approved on its own,
# and `publish` only goes through once all the required ones are approved.
# ============================================================================


def _asset_status_result(story, message: str) -> AssetStatusResponse:
    return AssetStatusResponse(
        message=message,
        story_id=story.id,
        content_status=story_data.asset_status_value(story.content_status),
        cover_status=story_data.asset_status_value(story.cover_status),
        voice_status=story_data.asset_status_value(story.voice_status),
        voice_not_required=bool(story.voice_not_required),
        publication_status=story_data.publication_status(story),
        published_at=_iso(story.published_at),
        publish_blockers=story_data.publish_blockers(story),
    )


def _approve_asset(
    db,
    story,
    asset: str,
    approved: bool,
    reviewed_by_id: str,
    notes: Optional[str] = None,
) -> AssetStatusResponse:
    target = AssetReviewStatus.approved if approved else AssetReviewStatus.ready_for_review
    story = story_data.set_asset_status(
        db, story, asset, target, reviewed_by_id=reviewed_by_id, notes=notes
    )
    label = {"content": "Written content", "cover": "Story card", "voice": "Voice"}[asset]
    verb = "approved" if approved else "sent back for review"
    return _asset_status_result(story, f"{label} {verb}")


@router.post(
    "/admin/moderation/story/{story_id}/approve-content",
    response_model=ApiResponse[AssetStatusResponse],
)
def approve_story_content(
    story_id: str,
    payload: Optional[AssetApprovalRequest] = Body(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Approve the written content only. Does not publish."""
    story = _require_story(db, story_id)
    approved = payload.approved if payload else True

    if approved and not (story.story_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This publication has no written content to approve.",
        )

    result = _approve_asset(
        db,
        story,
        "content",
        approved,
        str(current_user.id),
        notes=payload.notes if payload else None,
    )
    return success_response(result.message, status.HTTP_200_OK, result)


@router.post(
    "/admin/moderation/story/{story_id}/approve-cover",
    response_model=ApiResponse[AssetStatusResponse],
)
def approve_story_cover(
    story_id: str,
    payload: Optional[AssetApprovalRequest] = Body(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Approve the story card image and its details. Does not publish."""
    story = _require_story(db, story_id)
    approved = payload.approved if payload else True

    if approved and not (story.cover_image_url or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This publication has no story card image to approve.",
        )

    result = _approve_asset(
        db,
        story,
        "cover",
        approved,
        str(current_user.id),
        notes=payload.notes if payload else None,
    )
    return success_response(result.message, status.HTTP_200_OK, result)


@router.post(
    "/admin/moderation/story/{story_id}/approve-voice",
    response_model=ApiResponse[AssetStatusResponse],
)
def approve_story_voice(
    story_id: str,
    payload: Optional[AssetApprovalRequest] = Body(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Approve the narration. Does not publish."""
    story = _require_story(db, story_id)
    approved = payload.approved if payload else True

    if approved and not story.voice_not_required and not (story.audio_path or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This publication has no audio to approve. Mark it as having no voice instead.",
        )

    result = _approve_asset(
        db,
        story,
        "voice",
        approved,
        str(current_user.id),
        notes=payload.notes if payload else None,
    )
    return success_response(result.message, status.HTTP_200_OK, result)


@router.patch(
    "/admin/moderation/story/{story_id}/voice-requirement",
    response_model=ApiResponse[AssetStatusResponse],
)
def set_story_voice_requirement(
    story_id: str,
    payload: VoiceRequirementRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Mark a publication as intentionally having no voice, so publish skips it."""
    story = _require_story(db, story_id)
    story = story_data.set_voice_requirement(db, story, payload.voice_not_required)
    message = (
        "Publication marked as having no voice"
        if payload.voice_not_required
        else "Voice is required again"
    )
    return success_response(message, status.HTTP_200_OK, _asset_status_result(story, message))


@router.post(
    "/admin/moderation/story/{story_id}/publish",
    response_model=ApiResponse[PublishStoryResponse],
)
def publish_story(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Publish content, story card and voice together once all are approved."""
    story = _require_story(db, story_id)

    blockers = story_data.publish_blockers(story)
    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot publish yet: " + "; ".join(blockers),
        )

    story = story_data.publish_story(db, story, str(current_user.id))
    result = PublishStoryResponse(
        message="Publication is live",
        story_id=story.id,
        status=str(story.moderation_status).replace("ModerationStatus.", ""),
        publication_status=story_data.publication_status(story),
        published_at=_iso(story.published_at),
    )
    return success_response("Publication is live", status.HTTP_200_OK, result)


# ============================================================================
# Story card image
# ============================================================================


def _regenerate_cover_worker(story_id: str) -> None:
    """Regenerate one cover in the background, then park it for review."""
    import logging

    from app.core.db import SessionLocal
    from app.model.story import Story as StoryModel
    from app.utils.story_image_prompt import try_generate_story_cover

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        story = db.query(StoryModel).filter(StoryModel.id == story_id).first()
        if not story:
            return
        try:
            try_generate_story_cover(
                db,
                story,
                image_prompt=None,
                allow_admin_fallback=False,
                # The admin asked for this one by hand, so a member upload may go.
                replace_member_cover=True,
            )
        except Exception as exc:
            logger.error("Cover regen failed for story %s: %s", story_id, exc, exc_info=True)

        # Land on a real status either way so the card never sticks on "in progress".
        db.refresh(story)
        story.cover_status = (
            AssetReviewStatus.ready_for_review
            if (story.cover_image_url or "").strip()
            else AssetReviewStatus.missing
        )
        db.commit()
    finally:
        db.close()


@router.post(
    "/admin/moderation/story/{story_id}/regenerate-cover",
    response_model=ApiResponse[StoryCoverRegenResponse],
)
def regenerate_story_cover(
    story_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Queue a fresh AI story card for one publication."""
    story = _require_story(db, story_id)

    if not (story.story_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A story card needs written content to draw from.",
        )

    story = story_data.mark_cover_regenerating(db, story)
    background_tasks.add_task(_regenerate_cover_worker, str(story.id))

    result = StoryCoverRegenResponse(
        message="Story card regeneration started",
        story_id=story.id,
        cover_status=story_data.asset_status_value(story.cover_status),
    )
    return success_response(result.message, status.HTTP_202_ACCEPTED, result)


@router.post(
    "/admin/moderation/story/{story_id}/cover",
    response_model=ApiResponse[StoryCoverReplaceResponse],
)
async def replace_story_cover(
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Replace the story card image with an upload."""
    from app.utils.s3 import delete_s3_object, upload_image_to_s3

    story = _require_story(db, story_id)

    if file.content_type not in ALLOWED_COVER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type. Use JPEG, PNG, WebP or GIF.",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(payload) > MAX_COVER_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image is larger than 10 MB.",
        )

    extension = (file.filename or "").rsplit(".", 1)[-1].lower() or "jpg"
    image_url, image_key = upload_image_to_s3(payload, file_extension=extension)
    if not image_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not store the image. Try again.",
        )

    previous_key = story.cover_image_key
    story = story_data.set_story_cover(
        db, story, image_url, image_key, ImageSource.user_uploaded
    )
    if previous_key and previous_key != image_key:
        delete_s3_object(previous_key)

    result = StoryCoverReplaceResponse(
        message="Story card image replaced",
        story_id=story.id,
        cover_image_url=story.cover_image_url,
        cover_status=story_data.asset_status_value(story.cover_status),
    )
    return success_response(result.message, status.HTTP_200_OK, result)


# ============================================================================
# Narration audio
# ============================================================================


@router.post(
    "/admin/moderation/story/{story_id}/audio",
    response_model=ApiResponse[StoryAudioReplaceResponse],
)
async def replace_story_audio(
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Replace the narration with an uploaded recording."""
    import math

    from app.core.llm import save_audio
    from app.utils.media import get_mp3_duration

    story = _require_story(db, story_id)

    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported audio type. Use MP3, WAV, M4A or WebM.",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio is larger than 50 MB.",
        )

    try:
        audio_path = save_audio(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not store the audio. Try again.",
        ) from exc

    # Duration reading only works on MP3; fall back to the reading-speed estimate.
    duration_seconds = None
    try:
        exact = get_mp3_duration(payload)
        if exact and exact > 0:
            duration_seconds = int(math.ceil(exact))
    except Exception:
        duration_seconds = None
    if duration_seconds is None:
        words = len((story.story_text or "").split())
        duration_seconds = int((words / 150) * 60) or None

    story = story_data.set_story_audio(
        db,
        story,
        audio_path=audio_path,
        voice_name=story.voice_name,
        voice_id=story.voice_id,
        uses_custom_voice=bool(story.uses_custom_voice),
        audio_duration_seconds=duration_seconds,
        # An upload has no word timings, so drop the stale ones.
        alignment=[],
    )

    result = StoryAudioReplaceResponse(
        message="Narration replaced",
        story_id=story.id,
        audio_path=story.audio_path,
        audio_duration_seconds=story.audio_duration_seconds,
        voice_status=story_data.asset_status_value(story.voice_status),
    )
    return success_response(result.message, status.HTTP_200_OK, result)


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
