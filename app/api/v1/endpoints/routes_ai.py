import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.api.deps import get_current_admin_user, check_story_credit
from app.model.user import User
import app.data.story as story_data
import app.data.credit as credit_data
from app.schemas.schema_ai import (
    SearchResult,
    ResonanceRequest,
    ResonanceResponse,
    StoryGenerateRequest,
    StoryGenerateResponse,
    BulkGenerateRequest,
    SubmissionGenerateRequest,
    JobResponse,
    JobStatusResponse,
)
from app.schemas.schema_rag import IngestAllResponse, IngestNewRequest, IngestNewResponse
from app.services.service_ai import AIService
from app.services.service_rag import RAGService

router = APIRouter()


# ---------------------------------------------------------------------------
# Track search
# ---------------------------------------------------------------------------

@router.get("/ai/search", response_model=ApiResponse[SearchResult])
async def ai_search(query: str = Query(..., description="The user's query about how they feel")):
    """
    Takes a natural language query and returns the top 5 track IDs
    using vector similarity search.
    """
    result = AIService.search_tracks(query)
    return success_response("Track search completed", status.HTTP_200_OK, result)


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
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate resonance question: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Story generation (Confession / Meditation / Transformation)
# ---------------------------------------------------------------------------

@router.post("/ai/story/generate", response_model=ApiResponse[StoryGenerateResponse])
async def generate_story(
    request: StoryGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_story_credit),
):
    """
    Generates a personalised Confession, Meditation, or Transformation.

    Flow:
    1. Checks the user has available credits (free) or active subscription (premium).
    2. Creates a Story DB row in 'processing' state and returns immediately.
    3. SuperGrok generation + ElevenLabs TTS runs in the background.
    4. Poll GET /v1/admin/ai/status/{job_id} to check for completion and audio_path.

    Pass user profile context (age, life_phase, sliders) for maximum personalisation.
    """
    try:
        # Create a job_id and the Story DB row upfront — both in 'processing' state
        job_id = str(uuid.uuid4())

        story = story_data.create_story(
            db=db,
            story_type=request.story_type,
            job_id=job_id,
            user_id=str(current_user.id),
            admin_id=None,
            track_id=request.track_id,
            country_city=request.country_city,
            life_phase=request.life_phase,
            relationship_status=request.relationship_status,
            deepest_desire_fear=request.deepest_desire_fear,
            specific_trigger=request.specific_trigger,
            emotional_context={
                **(request.emotional_sliders or {}),
                **(request.session_sliders or {}),
            } or None,
            high_intensity=request.high_intensity,
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

        response = StoryGenerateResponse(
            story_id=str(story.id),
            job_id=job_id,
            story_text="",
            audio_path=None,
            message=f"Story generation queued. Poll /v1/admin/ai/status/{job_id} for updates.",
        )
        return success_response("Story generation queued", status.HTTP_200_OK, response)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate story generation: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Admin — Bulk generation
# ---------------------------------------------------------------------------

@router.post("/admin/ai/generate/bulk", response_model=ApiResponse[JobResponse])
async def admin_ai_generate_bulk(request: BulkGenerateRequest, background_tasks: BackgroundTasks):
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
    request: SubmissionGenerateRequest, background_tasks: BackgroundTasks
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
async def admin_ai_status(job_id: str):
    """
    Polling endpoint: returns the current status of a generation job.
    When status == 'completed', audio_path will contain the file location.
    """
    job = AIService.get_job_status(job_id)
    if not job:
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
