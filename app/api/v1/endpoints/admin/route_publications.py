"""One admin workspace and an explicit Publish step for each Confession or Meditation."""
from __future__ import annotations

import logging
import math
from io import BytesIO
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_admin_user
from app.core.db import SessionLocal, get_db
from app.core.responses import success_response
from app.data.publication import list_publications
from app.data import story as story_data
from app.model.story import (
    AssetReviewStatus,
    ImageSource,
    ModerationStatus,
    Story,
    StoryType,
)
from app.model.user import User
from app.schemas.schema_publication import PublicationListData, PublicationListItem, PublicationWorkspace
from app.schemas.schema_system import PaginationMeta
from app.utils.media import format_media_url, get_mp3_duration
from app.utils.publication_status import (
    asset_status,
    can_publish,
    overall_publication_status,
    public_author_name,
    publish_blockers,
    refresh_asset_statuses,
    utcnow,
)

router = APIRouter()
log = logging.getLogger(__name__)

COVER_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
AUDIO_TYPES = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


def _require_story(db: Session, story_id: str) -> Story:
    try:
        uid = UUID(story_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publication not found")
    story = (
        db.query(Story)
        .options(joinedload(Story.user).joinedload(User.profile))
        .filter(Story.id == uid)
        .filter(Story.story_type.in_([StoryType.confession, StoryType.meditation]))
        .first()
    )
    if not story:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publication not found")
    return story


def _enum(value) -> Optional[str]:
    if value is None:
        return None
    return value.value if getattr(value, "value", None) else str(value)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _list_item(story: Story) -> PublicationListItem:
    return PublicationListItem(
        id=str(story.id),
        title=story.title or "Untitled",
        author=public_author_name(story),
        story_type=_enum(story.story_type) or "confession",
        submitted_at=_iso(story.created_at) or "",
        updated_at=_iso(story.updated_at or story.created_at) or "",
        cover_image_url=format_media_url(story.cover_image_url),
        content_status=asset_status(story, "content"),
        cover_status=asset_status(story, "cover"),
        voice_status=asset_status(story, "voice"),
        publication_status=overall_publication_status(story),
        high_intensity=bool(story.high_intensity),
    )


def _workspace(story: Story) -> PublicationWorkspace:
    profile = story.user.profile if story.user else None
    return PublicationWorkspace(
        id=str(story.id),
        title=story.title,
        story_type=_enum(story.story_type) or "confession",
        first_name=story.first_name,
        location=story.location,
        gender=story.gender,
        sexual_orientation=story.sexual_orientation,
        occupation=story.occupation,
        age=story.age,
        high_intensity=bool(story.high_intensity),
        story_input=story.story_input,
        story_text=story.story_text,
        hero_hook=story.hero_hook,
        hero_tagline=story.hero_tagline,
        editorial_brief=story.editorial_brief,
        tags=story.tags if isinstance(story.tags, list) else None,
        growth_areas=story.growth_areas if isinstance(story.growth_areas, list) else None,
        life_phase=story.life_phase,
        submission_mode=_enum(story.submission_mode),
        cover_image_url=format_media_url(story.cover_image_url),
        content_status=asset_status(story, "content"),
        cover_status=asset_status(story, "cover"),
        voice_status=asset_status(story, "voice"),
        publication_status=overall_publication_status(story),
        can_publish=can_publish(story),
        publish_blockers=publish_blockers(story),
        submitted_at=_iso(story.created_at) or "",
        updated_at=_iso(story.updated_at or story.created_at) or "",
        published_at=_iso(story.published_at),
        voice={
            "voice_name": story.voice_name,
            "audio_path": format_media_url(story.audio_path),
            "duration_seconds": story.audio_duration_seconds,
            "generated_at": _iso(story.updated_at) if story.audio_path else None,
            "voice_not_required": bool(story.voice_not_required),
        },
        contact={
            "email": story.user.email if story.user else None,
            "true_name": profile.true_name if profile else None,
        },
    )


def _saved(db: Session, story: Story, message: str):
    db.commit()
    db.refresh(story)
    story = _require_story(db, str(story.id))
    return success_response(message, status.HTTP_200_OK, _workspace(story))


@router.get("/admin/publications")
def get_publications(
    search: Optional[str] = Query(None, max_length=200),
    story_type: Optional[Literal["confession", "meditation"]] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    missing: Optional[Literal["text", "cover", "voice"]] = None,
    sort: Literal["submitted_at", "updated_at"] = "submitted_at",
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    rows, total, stats = list_publications(
        db,
        search=search,
        story_type=story_type,
        publication_status=status_filter,
        missing=missing,
        sort=sort,
        limit=limit,
        offset=(page - 1) * limit,
    )
    total_pages = max(1, math.ceil(total / limit) if limit else 1)
    data = PublicationListData(
        items=[_list_item(story) for story in rows],
        all=stats.get("all", 0),
        missing=stats.get("missing", 0),
        pending=stats.get("pending", 0),
        in_progress=stats.get("in_progress", 0),
        ready_for_review=stats.get("ready_for_review", 0),
        ready_to_publish=stats.get("ready_to_publish", 0),
        published=stats.get("published", 0),
        rejected=stats.get("rejected", 0),
        meta=PaginationMeta(total=total, page=page, limit=limit, totalPages=total_pages),
    )
    return success_response("Publications fetched", status.HTTP_200_OK, data)


@router.get("/admin/publications/{story_id}")
def get_publication(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return success_response(
        "Publication fetched",
        status.HTTP_200_OK,
        _workspace(_require_story(db, story_id)),
    )


@router.post("/admin/publications/{story_id}/assets/{asset}/approve")
def approve_asset(
    story_id: str,
    asset: Literal["content", "cover", "voice"],
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    story = _require_story(db, story_id)
    state = asset_status(story, asset)
    if state in ("missing", "in_progress"):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is nothing finished to approve")
    if asset == "content" and not (story.story_text or "").strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "Written content is missing")
    if asset == "cover" and not (story.cover_image_url or "").strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "The story card needs a cover image")
    if asset == "cover" and not public_author_name(story):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The story card needs a public author name or pseudonym",
        )
    if asset == "voice" and not story.voice_not_required and not (story.audio_path or "").strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no audio to approve")

    setattr(story, f"{asset}_status", AssetReviewStatus.approved)
    if asset == "voice":
        story.voice_not_required = False
    return _saved(db, story, f"{asset} approved")


@router.post("/admin/publications/{story_id}/assets/{asset}/reject")
def reject_asset(
    story_id: str,
    asset: Literal["content", "cover", "voice"],
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    story = _require_story(db, story_id)
    setattr(story, f"{asset}_status", AssetReviewStatus.rejected)
    story.published_at = None
    if asset == "content":
        story.moderation_status = ModerationStatus.rejected
        story.moderation_reviewed_by = current_user.id
        story.moderation_reviewed_at = utcnow()
    elif getattr(story.moderation_status, "value", story.moderation_status) == "approved":
        story.moderation_status = ModerationStatus.pending
    return _saved(db, story, f"{asset} rejected")


@router.post("/admin/publications/{story_id}/voice/skip")
def skip_voice(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    story = _require_story(db, story_id)
    story.voice_not_required = True
    story.voice_status = AssetReviewStatus.approved
    return _saved(db, story, "Voice marked as not required")


@router.post("/admin/publications/{story_id}/publish")
def publish_publication(
    story_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    story = _require_story(db, story_id)
    if story.published_at is not None:
        return success_response("Already published", status.HTTP_200_OK, _workspace(story))
    blockers = publish_blockers(story)
    if blockers:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Not ready to publish. Still needs: {', '.join(blockers)}",
        )
    story.published_at = utcnow()
    story.moderation_status = ModerationStatus.approved
    story.moderation_reviewed_by = current_user.id
    story.moderation_reviewed_at = story.published_at
    response = _saved(db, story, "Published")
    background_tasks.add_task(_index_publication, str(story.id))
    return response


def _index_publication(story_id: str) -> None:
    try:
        from app.services.service_rag import RAGService

        with SessionLocal() as db:
            story = db.get(Story, UUID(story_id))
            if story and story.published_at:
                RAGService._embed_and_upsert([story])
    except Exception:
        log.exception("Publication search indexing failed for %s", story_id)


@router.post("/admin/publications/{story_id}/cover/regenerate")
def regenerate_cover(
    story_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    story = _require_story(db, story_id)
    if not (story.story_text or "").strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "Save the written content first")
    story.cover_status = AssetReviewStatus.in_progress
    db.commit()
    background_tasks.add_task(_cover_worker, str(story.id))
    return success_response("Cover regeneration started", status.HTTP_202_ACCEPTED, _workspace(story))


@router.post("/admin/publications/{story_id}/cover")
async def replace_cover(
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    data = await file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Image must be nonempty and at most 10 MB")
    ext = COVER_TYPES.get((file.content_type or "").lower())
    if not ext:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(BytesIO(data)) as image:
                ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}.get(image.format)
        except (UnidentifiedImageError, OSError):
            ext = None
    if not ext:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a valid JPEG, PNG, WebP, or GIF")

    story = _require_story(db, story_id)
    from app.utils.s3 import upload_image_to_s3

    url, key = upload_image_to_s3(data, file_extension=ext)
    if not url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Image storage failed")
    story_data.set_story_cover(db, story, url, key, ImageSource.admin_default)
    return success_response("Cover replaced", status.HTTP_200_OK, _workspace(_require_story(db, story_id)))


@router.post("/admin/publications/{story_id}/voice/regenerate")
def regenerate_voice(
    story_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    story = _require_story(db, story_id)
    if not (story.story_text or "").strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "Save the written content first")
    story.voice_status = AssetReviewStatus.in_progress
    story.voice_not_required = False
    db.commit()
    background_tasks.add_task(_voice_worker, str(story.id))
    return success_response("Voice regeneration started", status.HTTP_202_ACCEPTED, _workspace(story))


@router.post("/admin/publications/{story_id}/voice")
async def replace_voice(
    story_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    data = await file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Audio must be nonempty and at most 10 MB")
    ext = AUDIO_TYPES.get((file.content_type or "").lower())
    if not ext:
        name = (file.filename or "").lower()
        ext = next((value for key, value in (("mp3", "mp3"), ("wav", "wav"), ("m4a", "m4a"), ("ogg", "ogg"), ("webm", "webm")) if name.endswith("." + key)), None)
    if not ext:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a valid MP3, WAV, M4A, or OGG audio file")

    story = _require_story(db, story_id)
    from app.utils.s3 import upload_audio_bytes_to_s3

    url = upload_audio_bytes_to_s3(data, file_extension=ext)
    if not url:
        path = Path("media/audio") / f"{uuid4()}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        url = str(path)

    duration = None
    if ext == "mp3":
        seconds = get_mp3_duration(data)
        if seconds > 0:
            duration = int(math.ceil(seconds))

    story.audio_path = url
    story.audio_duration_seconds = duration
    story.alignment = None
    story.voice_not_required = False
    refresh_asset_statuses(story, force_voice=True)
    return _saved(db, story, "Audio replaced")


def _cover_worker(story_id: str) -> None:
    from app.utils.story_image_prompt import try_generate_story_cover

    with SessionLocal() as db:
        story = db.get(Story, UUID(story_id))
        if not story:
            return
        try:
            try_generate_story_cover(
                db,
                story,
                image_prompt=None,
                allow_admin_fallback=False,
                replace_member_cover=True,
            )
            refresh_asset_statuses(story, force_cover=True)
            db.commit()
        except Exception:
            log.exception("Cover regeneration failed for %s", story_id)
            story.cover_status = (
                AssetReviewStatus.ready_for_review
                if story.cover_image_url
                else AssetReviewStatus.missing
            )
            db.commit()


def _voice_worker(story_id: str) -> None:
    from app.services.service_ai import AIService

    with SessionLocal() as db:
        story = db.get(Story, UUID(story_id))
        if not story or not (story.story_text or "").strip():
            return
        try:
            voice_name, voice_id, uses_custom = AIService.resolve_voice(
                gender=story.gender,
                text=story.story_text,
                voice_name=story.voice_name,
                custom_voice_id=story.voice_id if story.uses_custom_voice else None,
            )
            audio_path, alignment = AIService.narrate_text(
                text=story.story_text,
                story_type=story.story_type,
                voice_id=voice_id,
            )
            story.voice_name = voice_name
            story.voice_id = voice_id
            story.uses_custom_voice = uses_custom
            story.audio_path = audio_path
            story.alignment = alignment
            refresh_asset_statuses(story, force_voice=True)
            db.commit()
        except Exception:
            log.exception("Voice regeneration failed for %s", story_id)
            story.voice_status = (
                AssetReviewStatus.ready_for_review
                if story.audio_path
                else AssetReviewStatus.missing
            )
            db.commit()
