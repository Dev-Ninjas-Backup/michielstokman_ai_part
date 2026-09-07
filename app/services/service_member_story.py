"""
app/services/service_member_story.py

Business logic for the member story workspace:
  - listing and inspecting a member's own submissions
  - editing a story and re-running it through the AI prompt
  - re-narrating an existing story with a different voice
  - withdrawing and resubmitting
  - cover imagery (AI generated or member uploaded)
  - Meta / Spotify distribution copy

Everything here is ownership-scoped: a story is only reachable through
`story_data.get_member_story`, which filters on the calling member's id.
"""
import json
import logging
import re
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import app.data.story as story_data
from app.core.config import settings
from app.core.llm import (
    ELEVENLABS_VOICES,
    MEMBER_VOICE_CATALOG,
    VoiceCloningError,
    canonical_voice_name,
    clone_voice_elevenlabs,
    delete_cloned_voice,
    get_story_llm,
    get_voice_preview_url,
    voice_preview_text,
    MIN_VOICE_SAMPLE_BYTES,
    MAX_VOICE_SAMPLE_BYTES,
)
from app.model.story import (
    GenerationStatus,
    ImageSource,
    ModerationStatus,
    Story,
    StoryType,
    SubmissionStatus,
)
from app.model.user import User
from app.schemas.schema_ai import StoryGenerateRequest
from app.schemas.schema_ai import StoryType as StoryTypeSchema
from app.schemas.schema_member_story import (
    CustomVoiceResponse,
    MemberStoryDetail,
    MemberStoryListItem,
    MemberStoryListResponse,
    RenarrateRequest,
    SharePackageResponse,
    SocialIntros,
    UpdateMemberStoryRequest,
    VoiceCatalogResponse,
    VoiceOption,
)
from app.schemas.schema_system import PaginationMeta
from app.services.service_ai import AIService
from app.utils.prompts import SOCIAL_INTRO_HUMAN, SOCIAL_INTRO_SYSTEM
from app.utils.text import story_card_excerpt
from app.utils.story_title import sync_active_title
from app.utils.story_image_prompt import try_generate_story_cover

logger = logging.getLogger(__name__)

STORY_REFERENCE_PREFIX = "TTL"


def public_story_share_url(story_id) -> str:
    return f"{settings.FRONTEND_URL}/details/{story_id}"


DEFAULT_VOICE_NAME = "Sophia"

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/webm", "audio/ogg", "audio/mp4", "audio/m4a", "audio/x-m4a",
}

# Only the opening of the story is sent to the intro writer. It is enough
# context for a teaser and keeps the prompt well inside the token budget.
SOCIAL_INTRO_EXCERPT_CHARS = 6000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def story_reference(story: Story) -> Optional[str]:
    """Formats the sequential story number as a member-facing reference."""
    if story.story_number is None:
        return None
    return f"{STORY_REFERENCE_PREFIX}-{story.story_number:06d}"


def _enum_value(value) -> Optional[str]:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _is_human_ready(story: Story) -> bool:
    return _enum_value(story.submission_mode) == "human_ready"


def _isoformat(value) -> Optional[str]:
    return value.isoformat() if value else None


def _get_profile(db: Session, user_id) -> Optional[object]:
    from app.model.profile import UserProfile

    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()


def _require_story(db: Session, user: User, story_id: str) -> Story:
    story = story_data.get_member_story(db, story_id, str(user.id))
    if not story:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    return story


def _require_not_processing(story: Story) -> None:
    if story.generation_status == GenerationStatus.processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This story is still being generated. Try again once it finishes.",
        )


def to_list_item(story: Story) -> MemberStoryListItem:
    return MemberStoryListItem(
        id=str(story.id),
        story_number=story.story_number,
        story_reference=story_reference(story),
        title=story.title,
        excerpt=story_card_excerpt(story),
        story_type=_enum_value(story.story_type),
        cover_image_url=story.cover_image_url,
        audio_path=story.audio_path,
        voice_name=story.voice_name,
        audio_duration_seconds=story.audio_duration_seconds,
        generation_status=_enum_value(story.generation_status),
        moderation_status=_enum_value(story.moderation_status),
        submission_status=_enum_value(story.submission_status),
        submission_mode=_enum_value(story.submission_mode) or "studio",
        has_social_intros=bool(story.social_intros),
        moderation_notes=story.moderation_notes,
        created_at=_isoformat(story.created_at),
    )


def to_detail(story: Story) -> MemberStoryDetail:
    return MemberStoryDetail(
        **to_list_item(story).model_dump(),
        member_title=story.member_title,
        ai_generated_title=story.ai_generated_title,
        use_ai_title=bool(story.use_ai_title),
        story_text=story.story_text,
        story_input=story.story_input,
        first_name=story.first_name,
        location=story.location,
        gender=story.gender,
        occupation=story.occupation,
        age=story.age,
        growth_areas=story.growth_areas,
        life_phase=story.life_phase,
        tags=story.tags,
        high_intensity=bool(story.high_intensity),
        uses_custom_voice=bool(story.uses_custom_voice),
        image_source=_enum_value(story.image_source),
        alignment=story.alignment,
        social_intros=story.social_intros if isinstance(story.social_intros, dict) else None,
        regeneration_count=story.regeneration_count or 0,
        withdrawn_at=_isoformat(story.withdrawn_at),
    )


class MemberStoryService:

    # -----------------------------------------------------------------------
    # Voice catalog and cloning
    # -----------------------------------------------------------------------

    @staticmethod
    def get_voice_catalog(db: Session, user: User) -> VoiceCatalogResponse:
        """Predefined narration voices, plus the member's cloned voice if present."""
        voices = []
        for voice in MEMBER_VOICE_CATALOG:
            voices.append(VoiceOption(
                **voice,
                is_custom=False,
                preview_url=get_voice_preview_url(
                    voice["name"],
                    voice_id=ELEVENLABS_VOICES.get(voice["name"]),
                    language=voice.get("language"),
                ),
                preview_text=voice_preview_text(voice.get("language")),
            ))

        custom = None
        profile = _get_profile(db, user.id)
        if profile and profile.custom_voice_id:
            custom_label = profile.custom_voice_name or "My Voice"
            custom = VoiceOption(
                name="custom",
                label=custom_label,
                gender="unspecified",
                language="unspecified",
                description="Your own recorded voice.",
                is_custom=True,
                preview_url=get_voice_preview_url(
                    f"custom-{profile.custom_voice_id}",
                    voice_id=profile.custom_voice_id,
                ),
                preview_text=voice_preview_text("english"),
            )

        return VoiceCatalogResponse(
            voices=voices,
            custom_voice=custom,
            default_voice=DEFAULT_VOICE_NAME,
        )

    @staticmethod
    def get_custom_voice(db: Session, user: User) -> CustomVoiceResponse:
        profile = _get_profile(db, user.id)
        if not profile or not profile.custom_voice_id:
            return CustomVoiceResponse(
                has_custom_voice=False,
                message="No voice recording uploaded yet.",
            )
        return CustomVoiceResponse(
            has_custom_voice=True,
            voice_name=profile.custom_voice_name,
            created_at=_isoformat(profile.custom_voice_created_at),
            message="Custom voice is ready to use for narration.",
        )

    @staticmethod
    def create_custom_voice(
        db: Session,
        user: User,
        recordings: list[UploadFile],
        display_name: Optional[str] = None,
    ) -> CustomVoiceResponse:
        """
        Clones the member's voice from one or more uploaded recordings.

        Requires an ElevenLabs plan with instant voice cloning enabled; when the
        provider refuses we return 503 so the client can fall back to the
        predefined voices rather than losing the member's upload silently.
        """
        from datetime import datetime, timezone

        if not recordings:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Upload at least one voice recording.",
            )

        samples = []
        for upload in recordings:
            content_type = (upload.content_type or "").lower()
            if content_type not in ALLOWED_AUDIO_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported audio format '{upload.content_type}'. Use mp3, wav, m4a, ogg or webm.",
                )
            data = upload.file.read()
            if len(data) < MIN_VOICE_SAMPLE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Recording is too short. Please record at least 30 seconds of clear speech.",
                )
            if len(data) > MAX_VOICE_SAMPLE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Recording is too large. Keep each file under 10 MB.",
                )
            samples.append((upload.filename or "sample.mp3", data, content_type))

        profile = _get_profile(db, user.id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complete your profile before recording a custom voice.",
            )

        # Replacing an existing clone: drop the old one from the provider first
        # so the account does not accumulate abandoned voices.
        if profile.custom_voice_id:
            delete_cloned_voice(profile.custom_voice_id)

        voice_label = (display_name or profile.true_name or "My Voice").strip()[:60]
        try:
            voice_id = clone_voice_elevenlabs(
                display_name=f"member-{user.id}-{voice_label}",
                samples=samples,
                description="Member-recorded narration voice for Transform to Liberation.",
            )
        except VoiceCloningError as exc:
            logger.warning(f"Voice cloning failed for user {user.id}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )

        profile.custom_voice_id = voice_id
        profile.custom_voice_name = voice_label
        profile.custom_voice_created_at = datetime.now(timezone.utc)
        db.commit()

        return CustomVoiceResponse(
            has_custom_voice=True,
            voice_name=voice_label,
            created_at=_isoformat(profile.custom_voice_created_at),
            message="Your voice is ready. Select it when generating or re-narrating a story.",
        )

    @staticmethod
    def delete_custom_voice(db: Session, user: User) -> CustomVoiceResponse:
        profile = _get_profile(db, user.id)
        if not profile or not profile.custom_voice_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No custom voice to delete.",
            )

        delete_cloned_voice(profile.custom_voice_id)
        profile.custom_voice_id = None
        profile.custom_voice_name = None
        profile.custom_voice_created_at = None
        db.commit()

        return CustomVoiceResponse(
            has_custom_voice=False,
            message="Custom voice removed. Existing narrations are unaffected.",
        )

    @staticmethod
    def _resolve_requested_voice(
        db: Session,
        user: User,
        voice_name: Optional[str],
        use_custom_voice: bool,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Validates a voice choice and returns (voice_name, custom_voice_id).
        Raises 422 when the member asks for a voice they cannot use.
        """
        if use_custom_voice:
            profile = _get_profile(db, user.id)
            if not profile or not profile.custom_voice_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No custom voice on file. Upload a recording first via POST /v1/me/voice.",
                )
            return profile.custom_voice_name or "My Voice", profile.custom_voice_id

        if voice_name:
            canonical = canonical_voice_name(voice_name)
            if not canonical:
                names = ", ".join(v["name"] for v in MEMBER_VOICE_CATALOG)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown voice '{voice_name}'. Choose one of: {names}.",
                )
            return canonical, None

        return None, None

    # -----------------------------------------------------------------------
    # Library
    # -----------------------------------------------------------------------

    @staticmethod
    def list_stories(
        db: Session,
        user: User,
        story_type: Optional[str] = None,
        submission_status: Optional[str] = None,
        generation_status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> MemberStoryListResponse:
        offset = (page - 1) * limit
        user_id = str(user.id)

        try:
            rows = story_data.list_member_stories(
                db, user_id, story_type, submission_status, generation_status, limit, offset
            )
            total = story_data.count_member_stories(
                db, user_id, story_type, submission_status, generation_status
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid filter value: {exc}",
            )

        counts = {"all": story_data.count_member_stories(db, user_id)}
        for state in SubmissionStatus:
            counts[state.value] = story_data.count_member_stories(
                db, user_id, submission_status=state.value
            )

        total_pages = (total + limit - 1) // limit if limit else 0
        return MemberStoryListResponse(
            stories=[to_list_item(row) for row in rows],
            counts=counts,
            meta=PaginationMeta(total=total, page=page, limit=limit, totalPages=total_pages),
        )

    @staticmethod
    def get_story(db: Session, user: User, story_id: str) -> MemberStoryDetail:
        return to_detail(_require_story(db, user, story_id))

    @staticmethod
    def delete_story(db: Session, user: User, story_id: str) -> str:
        story = _require_story(db, user, story_id)
        _require_not_processing(story)
        story_data.delete_story(db, story)
        return story_id

    # -----------------------------------------------------------------------
    # Withdraw / resubmit
    # -----------------------------------------------------------------------

    @staticmethod
    def withdraw(db: Session, user: User, story_id: str) -> Story:
        story = _require_story(db, user, story_id)
        if story.submission_status == SubmissionStatus.withdrawn:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This story is already withdrawn.",
            )
        return story_data.withdraw_story(db, story)

    @staticmethod
    def resubmit(db: Session, user: User, story_id: str) -> Story:
        story = _require_story(db, user, story_id)
        if story.submission_status != SubmissionStatus.withdrawn:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a withdrawn story can be resubmitted.",
            )
        _require_not_processing(story)
        if story.generation_status != GenerationStatus.completed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This story never finished generating and cannot be resubmitted.",
            )
        return story_data.resubmit_story(db, story)

    # -----------------------------------------------------------------------
    # Edit + regenerate
    # -----------------------------------------------------------------------

    @staticmethod
    def update_story(
        db: Session,
        user: User,
        story_id: str,
        payload: UpdateMemberStoryRequest,
    ) -> tuple[Story, Optional[str], Optional[str], Optional[str]]:
        """
        Applies the member's edits. When `regenerate` is set the story is pushed
        back through the AI prompt in the background and the caller receives a
        job id to poll.

        Returns (story, job_id | None, voice_name, custom_voice_id).
        """
        story = _require_story(db, user, story_id)
        _require_not_processing(story)

        if payload.title is not None:
            story.member_title = payload.title.strip() or None
            sync_active_title(story)
        if payload.use_ai_title is not None:
            if payload.use_ai_title and not (story.ai_generated_title or "").strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No AI-generated title is available yet for this story.",
                )
            story.use_ai_title = payload.use_ai_title
            sync_active_title(story)
        if payload.story_input is not None:
            cleaned = payload.story_input.strip()
            if not cleaned:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Story input cannot be empty.",
                )
            story.story_input = cleaned
        if payload.story_type is not None:
            story.story_type = StoryType(payload.story_type.value)
        if payload.growth_areas is not None:
            story.growth_areas = payload.growth_areas
        if payload.life_phase is not None:
            story.life_phase = payload.life_phase
        if payload.tags is not None:
            story.tags = payload.tags
        if payload.high_intensity is not None:
            story.high_intensity = payload.high_intensity

        if _is_human_ready(story):
            if payload.story_input is not None:
                story.story_text = story.story_input
            story.moderation_status = ModerationStatus.pending
            db.commit()
            db.refresh(story)
            return story, None, story.voice_name, None

        voice_name, custom_voice_id = MemberStoryService._resolve_requested_voice(
            db, user, payload.voice_name, bool(payload.use_custom_voice)
        )

        if not payload.regenerate:
            # Metadata-only correction. The narration no longer matches edited
            # source text, so send it back for moderation before it is published.
            story.moderation_status = ModerationStatus.pending
            db.commit()
            db.refresh(story)
            return story, None, voice_name, custom_voice_id

        if not story.story_input:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This story has no source text to regenerate from.",
            )

        job_id = str(uuid.uuid4())
        story_data.start_regeneration(db, story, job_id)
        return story, job_id, voice_name, custom_voice_id

    @staticmethod
    def regeneration_worker(
        job_id: str,
        story_db_id: str,
        voice_name: Optional[str],
        custom_voice_id: Optional[str],
    ):
        """
        Background task for an edited story: re-runs the AI prompt on the
        member's updated input, re-narrates it, and refreshes the cover.

        Opens its own session — the request session is closed by the time
        FastAPI runs background tasks.
        """
        from app.core.db import SessionLocal

        db = SessionLocal()
        story_row = None
        try:
            story_row = db.query(Story).filter(Story.id == uuid.UUID(story_db_id)).first()
            if not story_row:
                logger.error(f"[Regenerate {job_id}] Story {story_db_id} not found.")
                return

            profile = _get_profile(db, story_row.user_id) if story_row.user_id else None
            gender = profile.gender if profile else None

            if _is_human_ready(story_row):
                story_text = (story_row.story_input or "").strip()
                if not story_text:
                    raise ValueError("Fully narrated submissions need the finished text.")
                story_text_db = re.sub(r'<break\s+time="[^"]+"\s*/>', '', story_text)
                story_data.complete_story(
                    db=db,
                    story=story_row,
                    story_text=story_text_db,
                    title=None,
                    audio_path=story_row.audio_path,
                    audio_duration_seconds=story_row.audio_duration_seconds,
                    alignment=story_row.alignment,
                )
                AIService.persist_hero_hook(story_row, story_text_db)
                story_row.social_intros = None
                story_row.social_intros_generated_at = None
                if story_row.image_source != ImageSource.user_uploaded:
                    try_generate_story_cover(db, story_row, image_prompt=None)
                db.commit()
                logger.info(
                    f"[Regenerate {job_id}] Kept member narration for story {story_db_id}."
                )
                return

            request = StoryGenerateRequest(
                story_type=StoryTypeSchema(story_row.story_type.value),
                title=story_row.member_title or story_row.title,
                first_name=story_row.first_name,
                location=story_row.location,
                gender=story_row.gender,
                sexual_orientation=story_row.sexual_orientation,
                occupation=story_row.occupation,
                age=story_row.age,
                background=story_row.background,
                personality=story_row.personality,
                lifestyle=story_row.lifestyle,
                situation=story_row.situation,
                story_input=story_row.story_input,
                growth_areas=story_row.growth_areas or [],
                life_phase=story_row.life_phase,
                tags=story_row.tags or [],
                high_intensity=bool(story_row.high_intensity),
            )

            (
                title, story_text, audio_path, resolved_voice,
                image_prompt, alignment, voice_id, uses_custom,
            ) = AIService.generate_and_voice_story(
                request,
                gender=gender,
                voice_name=voice_name,
                custom_voice_id=custom_voice_id,
            )

            story_row.voice_name = resolved_voice
            story_row.voice_id = voice_id
            story_row.uses_custom_voice = uses_custom

            word_count = len(story_text.split()) if story_text else 0
            story_text_db = re.sub(r'<break\s+time="[^"]+"\s*/>', '', story_text)

            story_data.complete_story(
                db=db,
                story=story_row,
                story_text=story_text_db,
                title=title,
                audio_path=audio_path,
                audio_duration_seconds=int((word_count / 150) * 60),
                alignment=alignment,
            )

            AIService.persist_hero_hook(story_row, story_text_db)

            # The story text changed, so any previously generated distribution
            # copy no longer describes it.
            story_row.social_intros = None
            story_row.social_intros_generated_at = None

            if story_row.image_source != ImageSource.user_uploaded:
                try_generate_story_cover(db, story_row, image_prompt=image_prompt)

            db.commit()
            logger.info(f"[Regenerate {job_id}] Completed for story {story_db_id}.")

        except Exception as exc:
            logger.error(f"[Regenerate {job_id}] FAILED: {exc}", exc_info=True)
            try:
                if story_row:
                    story_data.fail_story(db=db, story=story_row)
            except Exception:
                logger.warning(f"[Regenerate {job_id}] Could not record failure state.", exc_info=True)
        finally:
            db.close()

    # -----------------------------------------------------------------------
    # Re-narrate
    # -----------------------------------------------------------------------

    @staticmethod
    def start_renarration(
        db: Session,
        user: User,
        story_id: str,
        payload: RenarrateRequest,
    ) -> tuple[Story, str, Optional[str], Optional[str]]:
        """
        Validates a request to re-record the existing text with a different
        voice. Returns (story, job_id, voice_name, custom_voice_id).
        """
        story = _require_story(db, user, story_id)
        _require_not_processing(story)

        if _is_human_ready(story):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Fully narrated submissions keep the uploaded recording. Voice cannot be changed.",
            )

        if not story.story_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This story has no text to narrate yet.",
            )
        if not payload.voice_name and not payload.use_custom_voice:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose a voice_name or set use_custom_voice.",
            )

        voice_name, custom_voice_id = MemberStoryService._resolve_requested_voice(
            db, user, payload.voice_name, payload.use_custom_voice
        )

        job_id = str(uuid.uuid4())
        story.job_id = job_id
        story.generation_status = GenerationStatus.processing
        db.commit()
        db.refresh(story)
        return story, job_id, voice_name, custom_voice_id

    @staticmethod
    def renarration_worker(
        job_id: str,
        story_db_id: str,
        voice_name: Optional[str],
        custom_voice_id: Optional[str],
    ):
        """
        Background task: re-runs TTS over the stored story text with the newly
        chosen voice. The text itself is left untouched.
        """
        from app.core.db import SessionLocal

        db = SessionLocal()
        story_row = None
        try:
            story_row = db.query(Story).filter(Story.id == uuid.UUID(story_db_id)).first()
            if not story_row:
                logger.error(f"[Renarrate {job_id}] Story {story_db_id} not found.")
                return

            profile = _get_profile(db, story_row.user_id) if story_row.user_id else None
            resolved_name, resolved_id, uses_custom = AIService.resolve_voice(
                gender=profile.gender if profile else None,
                text=story_row.story_text,
                voice_name=voice_name,
                custom_voice_id=custom_voice_id,
            )

            audio_path, alignment = AIService.narrate_text(
                text=story_row.story_text,
                story_type=story_row.story_type.value,
                voice_id=resolved_id,
            )

            old_audio = story_row.audio_path
            word_count = len(story_row.story_text.split())
            story_data.set_story_audio(
                db=db,
                story=story_row,
                audio_path=audio_path,
                voice_name=resolved_name,
                voice_id=resolved_id,
                uses_custom_voice=uses_custom,
                audio_duration_seconds=int((word_count / 150) * 60),
                alignment=alignment,
            )
            logger.info(f"[Renarrate {job_id}] Story {story_db_id} re-narrated with {resolved_name}. "
                        f"Previous audio: {old_audio}")

        except Exception as exc:
            logger.error(f"[Renarrate {job_id}] FAILED: {exc}", exc_info=True)
            try:
                if story_row:
                    story_data.fail_story(db=db, story=story_row)
            except Exception:
                logger.warning(f"[Renarrate {job_id}] Could not record failure state.", exc_info=True)
        finally:
            db.close()

    # -----------------------------------------------------------------------
    # Imagery
    # -----------------------------------------------------------------------

    @staticmethod
    def store_uploaded_image(image: UploadFile) -> tuple[str, str]:
        """
        Validates a member-supplied cover and stores it. Returns (url, key).
        Used both at story creation and when replacing artwork later.
        """
        from app.utils.s3 import upload_image_to_s3

        content_type = (image.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported image format. Use JPEG, PNG or WebP.",
            )

        data = image.file.read()
        if not data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The uploaded image is empty.",
            )
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Image is too large. Keep it under 8 MB.",
            )

        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
        image_url, image_key = upload_image_to_s3(data, file_extension=extension)
        if not image_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not store the image right now. Please try again.",
            )
        return image_url, image_key

    @staticmethod
    def upload_story_image(db: Session, user: User, story_id: str, image: UploadFile) -> Story:
        """Replaces the story cover with an image the member supplies."""
        from app.utils.s3 import delete_s3_object

        story = _require_story(db, user, story_id)
        image_url, image_key = MemberStoryService.store_uploaded_image(image)
        previous_key = story.cover_image_key
        story_data.set_story_cover(db, story, image_url, image_key, ImageSource.user_uploaded)
        if previous_key:
            delete_s3_object(previous_key)
        return story

    @staticmethod
    def generate_story_image(db: Session, user: User, story_id: str) -> Story:
        """
        Regenerates the AI cover art from the story's own content, matching the
        palette and composition rules defined for its type.
        """
        from app.utils.story_image_prompt import try_generate_story_cover

        story = _require_story(db, user, story_id)
        _require_not_processing(story)

        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI image generation is not configured on this server.",
            )
        if not story.story_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Generate the story before creating its artwork.",
            )

        try_generate_story_cover(
            db,
            story,
            image_prompt=None,
            allow_admin_fallback=False,
            replace_member_cover=True,
        )
        db.commit()
        db.refresh(story)
        if not story.cover_image_url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The image provider could not generate artwork for this story. Please try again.",
            )
        return story

    # -----------------------------------------------------------------------
    # Meta / Spotify distribution
    # -----------------------------------------------------------------------

    @staticmethod
    def generate_social_intros(
        db: Session,
        user: User,
        story_id: str,
        force: bool = False,
    ) -> Story:
        """
        Produces the platform-specific introductions: a short teaser for
        Instagram and Facebook, and a longer one for Spotify.
        """
        story = _require_story(db, user, story_id)

        if story.social_intros and not force:
            return story
        if not story.story_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Generate the story before preparing it for sharing.",
            )

        intros = MemberStoryService._invoke_social_intro_llm(story)
        return story_data.set_social_intros(db, story, intros)

    @staticmethod
    def _invoke_social_intro_llm(story: Story) -> dict:
        from langchain_core.prompts import (
            ChatPromptTemplate,
            HumanMessagePromptTemplate,
            SystemMessagePromptTemplate,
        )

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(SOCIAL_INTRO_SYSTEM),
            HumanMessagePromptTemplate.from_template(SOCIAL_INTRO_HUMAN),
        ])
        messages = chat_prompt.format_prompt(
            story_type=story.story_type.value,
            title=story.title or "Untitled",
            author_name=story.first_name or "Anonymous",
            tags=", ".join(story.tags) if story.tags else "None",
            growth_areas=", ".join(story.growth_areas) if story.growth_areas else "None",
            story_excerpt=(story.story_text or "")[:SOCIAL_INTRO_EXCERPT_CHARS],
        ).to_messages()

        try:
            response = get_story_llm(temperature=0.7).invoke(messages)
        except Exception as exc:
            logger.error(f"Social intro generation failed for story {story.id}: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The writing service is unavailable right now. Please try again.",
            )

        parsed = MemberStoryService._parse_intro_json(response.content)
        if not parsed:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not produce usable introductions. Please try again.",
            )
        return parsed

    @staticmethod
    def _parse_intro_json(raw: str) -> Optional[dict]:
        """Extracts the intro object, tolerating code fences or stray prose."""
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        if not isinstance(data, dict):
            return None

        result = {}
        for platform in ("instagram", "facebook", "spotify"):
            value = data.get(platform)
            if not isinstance(value, str) or not value.strip():
                return None
            result[platform] = value.strip()
        return result

    @staticmethod
    def get_share_package(db: Session, user: User, story_id: str) -> SharePackageResponse:
        """
        Assembles everything needed to publish to Meta or Spotify: the existing
        artwork, the audio, and the platform introductions. Intros are generated
        on first request so the client never has to make two calls.
        """
        story = _require_story(db, user, story_id)

        if not story.social_intros:
            story = MemberStoryService.generate_social_intros(db, user, story_id)

        return SharePackageResponse(
            story_id=str(story.id),
            story_number=story.story_number,
            story_reference=story_reference(story),
            title=story.title,
            story_type=_enum_value(story.story_type),
            author_name=story.first_name,
            cover_image_url=story.cover_image_url,
            audio_url=story.audio_path,
            audio_duration_seconds=story.audio_duration_seconds,
            share_url=public_story_share_url(story.id),
            intros=SocialIntros(**story.social_intros),
            generated_at=_isoformat(story.social_intros_generated_at),
        )
