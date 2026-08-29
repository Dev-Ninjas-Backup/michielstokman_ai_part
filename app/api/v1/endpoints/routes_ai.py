import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Depends, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_admin_user, get_current_user
from app.model.user import User
import app.data.story as story_data
import app.data.credit as credit_data
from app.schemas.schema_ai import (
    CoverImageMode,
    CoverPreviewRequest,
    CoverPreviewResponse,
    SearchResult,
    ResonanceRequest,
    ResonanceResponse,
    StoryGenerateRequest,
    StoryGenerateResponse,
    BulkGenerateRequest,
    SubmissionGenerateRequest,
    JobResponse,
    JobStatusResponse,
    multipart_image,
    multipart_audio,
)
from app.schemas.schema_rag import IngestAllResponse, IngestNewRequest, IngestNewResponse
from app.services.service_ai import AIService
from app.services.service_rag import RAGService

router = APIRouter()


# ---------------------------------------------------------------------------
# Track search
# ---------------------------------------------------------------------------

@router.get("/ai/search", response_model=ApiResponse[SearchResult])
async def ai_search(
    query: str = Query(None, alias="q", description="The user's query about how they feel"),
    q: str = Query(None, description="Alias: same as 'query' — the user's query"),
):
    """
    Takes a natural language query and returns the top 5 track IDs
    using vector similarity search. Pass as ?q=your+query or ?query=your+query
    """
    search_query = query or q
    if not search_query:
        raise HTTPException(status_code=422, detail="Query parameter 'q' is required")
    try:
        result = AIService.search_tracks(search_query)
        return success_response("Track search completed", status.HTTP_200_OK, result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI search unavailable: {str(e)[:100]}")


# ---------------------------------------------------------------------------
# Resonance (journaling question)
# ---------------------------------------------------------------------------

@router.post("/ai/resonance", response_model=ApiResponse[ResonanceResponse])
async def generate_resonance_question(request: ResonanceRequest):
    """
    Takes track logic and user emotional sliders and generates a deeply
    reflective journaling question via SuperGrok.
    """
    try:
        result = AIService.generate_resonance_question(request)
        return success_response("Resonance question generated", status.HTTP_200_OK, result)
    except Exception as e:
        err = str(e)
        if "API key" in err or "Incorrect API" in err:
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable — API key not configured on server."
            )
        raise HTTPException(status_code=500, detail=f"Failed to generate resonance question: {err[:200]}")


async def _parse_story_generate(http_request: Request) -> tuple[StoryGenerateRequest, Optional[object], Optional[object]]:
    """
    Accepts JSON (AI artwork + our voices) or multipart/form-data
    (own cover and/or finished narration).
    """
    content_type = (http_request.headers.get("content-type") or "").lower()
    try:
        if "multipart/form-data" in content_type:
            form = await http_request.form()
            payload = StoryGenerateRequest.from_multipart(form)
            return payload, multipart_image(form), multipart_audio(form)
        body = await http_request.json()
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Request body must be a JSON object or multipart form.",
            )
        return StoryGenerateRequest.model_validate(body), None, None
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = " -> ".join(str(part) for part in first.get("loc", []) if part != "body")
        msg = first.get("msg") or "Invalid request."
        detail = f"{loc}: {msg}" if loc else msg
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request body must be JSON or multipart/form-data.",
        )


# ---------------------------------------------------------------------------
# Cover preview (generate artwork on the create form, before submit)
# ---------------------------------------------------------------------------

@router.post(
    "/ai/story/cover-preview",
    response_model=ApiResponse[CoverPreviewResponse],
)
def preview_story_cover(
    request: CoverPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates cover artwork from the member's title, identity, and draft text
    so they can see it on the create form before submitting the story.
    Does not create a story or deduct a credit.
    """
    from app.data.credit import has_credits
    from app.utils.story_image_prompt import generate_cover_from_draft

    if not has_credits(db, str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Daily credit limit reached. Upgrade to Premium for unlimited stories.",
        )

    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI image generation is not configured on this server.",
        )

    try:
        cover_url, cover_key = generate_cover_from_draft(
            story_type=request.story_type.value,
            title=request.title,
            first_name=request.first_name,
            location=request.location,
            gender=request.gender,
            occupation=request.occupation,
            age=request.age,
            story_input=request.story_input,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not generate cover artwork: {str(exc)[:200]}",
        ) from exc

    if not cover_url or not cover_key:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The image provider could not generate artwork. Please try again, or upload your own image.",
        )

    result = CoverPreviewResponse(
        cover_image_url=cover_url,
        cover_image_key=cover_key,
    )
    return success_response("Cover artwork generated", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# Story generation (Confession / Meditation / Transformation)
# ---------------------------------------------------------------------------

@router.post(
    "/ai/story/generate",
    response_model=ApiResponse[StoryGenerateResponse],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/StoryGenerateRequest"},
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["story_type", "story_input"],
                        "properties": {
                            "story_type": {
                                "type": "string",
                                "enum": ["confession", "meditation", "transformation"],
                            },
                            "title": {"type": "string"},
                            "first_name": {"type": "string"},
                            "location": {"type": "string"},
                            "gender": {"type": "string"},
                            "occupation": {"type": "string"},
                            "age": {"type": "integer"},
                            "story_input": {"type": "string"},
                            "growth_areas": {"type": "string", "description": "JSON array or comma-separated"},
                            "life_phase": {"type": "string"},
                            "tags": {"type": "string", "description": "JSON array or comma-separated"},
                            "high_intensity": {"type": "boolean"},
                            "voice_name": {"type": "string"},
                            "use_custom_voice": {"type": "boolean"},
                            "image_mode": {
                                "type": "string",
                                "enum": ["ai_generated", "user_uploaded"],
                            },
                            "preview_cover_key": {
                                "type": "string",
                                "description": "Key from POST /ai/story/cover-preview.",
                            },
                            "image": {
                                "type": "string",
                                "format": "binary",
                                "description": "Member's cover image. JPEG, PNG or WebP, up to 8 MB.",
                            },
                        },
                    }
                },
            },
        }
    },
)
async def generate_story(
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates a personalised Confession, Meditation, or Transformation.

    Flow:
    1. Checks the user has available credits (free) or active subscription (premium).
    2. Creates a Story DB row in 'processing' state and returns immediately.
    3. SuperGrok generation + ElevenLabs TTS runs in the background.
    4. Poll GET /v1/me/stories/{story_id} until generation_status is completed.

    Cover art is chosen on this same request:
    - JSON, or multipart without an `image` file → AI-generated artwork
      (`image_mode` defaults to `ai_generated`). Pass `preview_cover_key` from
      POST /ai/story/cover-preview to attach that image and skip a second draw.
    - multipart/form-data with field `image` → the uploaded file becomes the
      cover immediately. `image_mode` is set to `user_uploaded` and no AI
      image is generated.

    The later `POST /v1/me/stories/{id}/image` endpoint is only for replacing
    artwork after creation.
    """
    request, uploaded_image, uploaded_audio = await _parse_story_generate(http_request)

    # An attached file is the member choosing their own cover — even if they
    # forgot to set image_mode.
    if uploaded_image is not None:
        request.image_mode = CoverImageMode.user_uploaded
    elif request.image_mode == CoverImageMode.user_uploaded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "To use your own image, send this request as multipart/form-data "
                "and attach the file as `image`. To have the story illustrated "
                "for you, omit image_mode or set it to ai_generated."
            ),
        )

    from app.data.credit import has_credits

    if not has_credits(db, str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Daily credit limit reached. Upgrade to Premium for unlimited stories.",
        )

    # Fail fast if the member asked to narrate in a voice they have not recorded,
    # rather than silently falling back to a stock voice inside the worker.
    if request.use_custom_voice:
        from app.model.profile import UserProfile

        profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        if not profile or not profile.custom_voice_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No custom voice on file. Upload a recording first via POST /v1/me/voice.",
            )

    cover_url = None
    cover_key = None
    preview_attached = False
    if uploaded_image is not None:
        from app.services.service_member_story import MemberStoryService

        cover_url, cover_key = MemberStoryService.store_uploaded_image(uploaded_image)
    elif request.preview_cover_key:
        from app.utils.s3 import resolve_stored_image_key

        cover_url, cover_key = resolve_stored_image_key(request.preview_cover_key)
        if not cover_url or not cover_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Generate cover artwork on this form first, then submit.",
            )
        preview_attached = True

    member_audio_path = None
    if uploaded_audio is not None:
        from app.core.llm import save_audio, MAX_VOICE_SAMPLE_BYTES
        from app.services.service_member_story import ALLOWED_AUDIO_TYPES

        content_type = (uploaded_audio.content_type or "").lower()
        if content_type not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Narration must be mp3, wav, m4a, ogg or webm.",
            )
        audio_bytes = await uploaded_audio.read()
        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The narration file was empty.",
            )
        if len(audio_bytes) > MAX_VOICE_SAMPLE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Narration file must be 10 MB or smaller.",
            )
        member_audio_path = save_audio(audio_bytes)
        request.skip_narration = True
        request.use_custom_voice = False
    elif request.skip_narration:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="To use your own narration, attach the finished audio as multipart field `audio`.",
        )

    try:
        # Create a job_id and the Story DB row upfront — both in 'processing' state
        job_id = str(uuid.uuid4())

        from app.model.story import ImageSource

        if uploaded_image is not None:
            image_source = ImageSource.user_uploaded
        elif preview_attached:
            image_source = ImageSource.ai_generated
        else:
            image_source = None

        story = story_data.create_story(
            db=db,
            story_type=request.story_type,
            job_id=job_id,
            user_id=str(current_user.id),
            admin_id=None,
            title=request.title,
            first_name=request.first_name,
            location=request.location,
            gender=request.gender,
            occupation=request.occupation,
            age=request.age,
            story_input=request.story_input,
            growth_areas=request.growth_areas,
            life_phase=request.life_phase,
            tags=request.tags,
            high_intensity=request.high_intensity,
            cover_image_url=cover_url,
            cover_image_key=cover_key,
            image_source=image_source,
            audio_path=member_audio_path,
        )

        # Deduct 1 credit (no-op for premium users)
        credit_data.deduct_credit(db, str(current_user.id))

        # Queue the heavy generation work as a background task
        background_tasks.add_task(
            AIService.story_generation_worker,
            job_id=job_id,
            request=request,
            story_db_id=str(story.id),
        )

        from app.services.service_member_story import story_reference

        if request.image_mode == CoverImageMode.user_uploaded:
            message = (
                "Story generation queued with your uploaded cover. "
                f"Poll /v1/me/stories/{story.id} for progress."
            )
        else:
            message = f"Story generation queued. Poll /v1/me/stories/{story.id} for updates."

        response = StoryGenerateResponse(
            story_id=str(story.id),
            story_number=story.story_number,
            story_reference=story_reference(story),
            job_id=job_id,
            voice_name=request.voice_name,
            image_mode=request.image_mode,
            cover_image_url=story.cover_image_url,
            title=story.title,
            story_text="",
            audio_path=None,
            message=message,
        )
        return success_response("Story generation queued", status.HTTP_200_OK, response)

    except HTTPException:
        if cover_key and not preview_attached:
            from app.utils.s3 import delete_s3_object
            delete_s3_object(cover_key)
        raise
    except Exception as e:
        if cover_key and not preview_attached:
            from app.utils.s3 import delete_s3_object
            delete_s3_object(cover_key)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate story generation: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Admin — Bulk generation
# ---------------------------------------------------------------------------

@router.post("/admin/ai/generate/bulk", response_model=ApiResponse[JobResponse])
async def admin_ai_generate_bulk(
    request: BulkGenerateRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_current_admin_user),
):
    """
    Admin endpoint: takes a topic and story type, spawns a long-running
    bulk generation task. Returns a job ID instantly.
    """
    job_id = AIService.initiate_bulk_generation(
        request.topic, request.story_type.value, request.format
    )
    background_tasks.add_task(
        AIService.bulk_generation_worker,
        job_id,
        request.topic,
        request.story_type.value,
        request.format,
    )
    result = JobResponse(job_id=job_id, message="Bulk generation job queued successfully.")
    return success_response("Bulk generation job queued", status.HTTP_200_OK, result)


@router.post("/admin/ai/generate/submission", response_model=ApiResponse[JobResponse])
async def admin_ai_generate_submission(
    request: SubmissionGenerateRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_current_admin_user),
):
    """
    Triggers background AI processing based on an existing submission.
    Returns a job ID instantly.
    """
    job_id = AIService.initiate_submission_generation(request.submission_id)
    background_tasks.add_task(
        AIService.submission_generation_worker, job_id, request.submission_id
    )
    result = JobResponse(job_id=job_id, message="Submission generation job queued successfully.")
    return success_response("Submission generation job queued", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# Job status polling
# ---------------------------------------------------------------------------

@router.get("/admin/ai/status/{job_id}", response_model=ApiResponse[JobStatusResponse])
async def admin_ai_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Polling endpoint: returns the current status of a generation job.
    When status == 'completed', audio_path will contain the file location.

    Members can poll their own jobs; admins can poll any job.
    """
    job = AIService.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    owner_id = job.get("owner_user_id")
    if owner_id and not current_user.is_admin and owner_id != str(current_user.id):
        # 404 rather than 403 so job ids cannot be probed for existence.
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    result = JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        title=job.get("title"),
        audio_path=job.get("audio_path"),
        story_text=job.get("story_text"),
    )
    return success_response("Job status retrieved", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# RAG Ingestion — Admin only
# ---------------------------------------------------------------------------

@router.post("/ai/rag/ingest/all", response_model=ApiResponse[IngestAllResponse])
async def rag_ingest_all(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Full re-index: embed all completed stories and upsert into Pinecone.
    Admin-only endpoint.
    """
    try:
        count = RAGService.ingest_all_stories(db)
        result = IngestAllResponse(
            total_stories_indexed=count,
            message=f"Full re-index completed. {count} stories indexed.",
        )
        return success_response("RAG full ingestion completed", status.HTTP_200_OK, result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RAG full ingestion failed: {str(e)}",
        )


@router.post("/ai/rag/ingest/new", response_model=ApiResponse[IngestNewResponse])
async def rag_ingest_new(
    body: IngestNewRequest = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Incremental index: embed only stories created after the given timestamp.
    Defaults to the last 24 hours if no `since` is provided.
    Admin-only endpoint.
    """
    try:
        since = body.since if body else None
        count = RAGService.ingest_new_stories(db, since=since)
        result = IngestNewResponse(
            new_stories_indexed=count,
            message=f"Incremental index completed. {count} new stories indexed.",
        )
        return success_response("RAG incremental ingestion completed", status.HTTP_200_OK, result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RAG incremental ingestion failed: {str(e)}",
        )


@router.post("/ai/rag/ingest/tracks", response_model=ApiResponse[dict])
async def rag_ingest_tracks(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Embed all approved liberation definitions and upsert into Pinecone.
    Admin-only endpoint.
    """
    try:
        count = RAGService.ingest_liberation_definitions(db)
        return success_response(
            "Track ingestion completed",
            status.HTTP_200_OK,
            {"total_tracks_indexed": count, "message": f"{count} tracks indexed."}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Track ingestion failed: {str(e)}",
        )
