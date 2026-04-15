import uuid
from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
import app.data.story as story_data
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
from app.services.service_ai import AIService

router = APIRouter()


# ---------------------------------------------------------------------------
# Track search
# ---------------------------------------------------------------------------

@router.get("/ai/search", response_model=SearchResult)
async def ai_search(query: str = Query(..., description="The user's query about how they feel")):
    """
    Takes a natural language query and returns the top 5 track IDs
    using vector similarity search.
    """
    return AIService.search_tracks(query)


# ---------------------------------------------------------------------------
# Resonance (journaling question)
# ---------------------------------------------------------------------------

@router.post("/ai/resonance", response_model=ResonanceResponse)
async def generate_resonance_question(request: ResonanceRequest):
    """
    Takes track logic and user emotional sliders and generates a deeply
    reflective journaling question via SuperGrok.
    """
    try:
        return AIService.generate_resonance_question(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate resonance question: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Story generation (Confession / Meditation / Transformation)
# ---------------------------------------------------------------------------

@router.post("/ai/story/generate", response_model=StoryGenerateResponse)
async def generate_story(
    request: StoryGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    # TODO: extract user_id from JWT token once auth middleware is wired up
    # current_user: User = Depends(get_current_user),
):
    """
    Generates a personalised Confession, Meditation, or Transformation.

    Flow:
    1. Creates a Story DB row in 'processing' state and returns immediately.
    2. SuperGrok generation + ElevenLabs TTS runs in the background.
    3. Poll GET /v1/admin/ai/status/{job_id} to check for completion and audio_path.

    Pass user profile context (age, life_phase, sliders) for maximum personalisation.
    """
    try:
        # Create a job_id and the Story DB row upfront — both in 'processing' state
        job_id = str(uuid.uuid4())

        story = story_data.create_story(
            db=db,
            story_type=request.story_type,
            job_id=job_id,
            user_id=None,       # TODO: replace with current_user.id from JWT
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

        # Queue the heavy generation work as a background task
        background_tasks.add_task(
            AIService.story_generation_worker,
            job_id=job_id,
            request=request,
            story_db_id=str(story.id),
        )

        return StoryGenerateResponse(
            story_id=str(story.id),
            job_id=job_id,
            story_text="",
            audio_path=None,
            message=f"Story generation queued. Poll /v1/admin/ai/status/{job_id} for updates.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate story generation: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Admin — Bulk generation
# ---------------------------------------------------------------------------

@router.post("/admin/ai/generate/bulk", response_model=JobResponse)
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
    return JobResponse(job_id=job_id, message="Bulk generation job queued successfully.")


@router.post("/admin/ai/generate/submission", response_model=JobResponse)
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
    return JobResponse(job_id=job_id, message="Submission generation job queued successfully.")


# ---------------------------------------------------------------------------
# Job status polling
# ---------------------------------------------------------------------------

@router.get("/admin/ai/status/{job_id}", response_model=JobStatusResponse)
async def admin_ai_status(job_id: str):
    """
    Polling endpoint: returns the current status of a generation job.
    When status == 'completed', audio_path will contain the file location.
    """
    job = AIService.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        title=job.get("title"),
        audio_path=job.get("audio_path"),
        story_text=job.get("story_text"),
    )

