from fastapi import APIRouter, BackgroundTasks, Query, HTTPException

from app.schemas.schema_ai import (
    SearchResult,
    ResonanceRequest,
    ResonanceResponse,
    BulkGenerateRequest,
    SubmissionGenerateRequest,
    JobResponse,
    JobStatusResponse
)
from app.services.service_ai import AIService

router = APIRouter()

@router.get("/ai/search", response_model=SearchResult)
async def ai_search(query: str = Query(..., description="The user's query about how they feel")):
    """
    Takes a natural language query and returns the top 5 track IDs using vector similarity.
    All logic is deferred to the AIService layer.
    """
    return AIService.search_tracks(query)

@router.post("/ai/resonance", response_model=ResonanceResponse)
async def generate_resonance_question(request: ResonanceRequest):
    """
    Takes track logic and user emotional sliders to generate a deeply reflective journaling question.
    """
    try:
        return AIService.generate_resonance_question(request)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate resonance question: {str(e)}"
        )

@router.post("/admin/ai/generate/bulk", response_model=JobResponse)
async def admin_ai_generate_bulk(request: BulkGenerateRequest, background_tasks: BackgroundTasks):
    """
    Takes a topic and format and spawns a long-running generation task. Returns job ID instantly.
    """
    # 1. Ask the service to lock in a new job ID
    job_id = AIService.initiate_bulk_generation(request.topic, request.format)
    
    # 2. Hand off the heavy ElevenLabs / Langchain execution to FastAPI BackgroundTasks
    background_tasks.add_task(AIService.bulk_generation_worker, job_id, request.topic, request.format)
    
    return JobResponse(job_id=job_id, message="Bulk generation job queued successfully.")

@router.post("/admin/ai/generate/submission", response_model=JobResponse)
async def admin_ai_generate_submission(request: SubmissionGenerateRequest, background_tasks: BackgroundTasks):
    """
    Triggers background AI processing based on an existing submission. Returns instantly.
    """
    job_id = AIService.initiate_submission_generation(request.submission_id)
    background_tasks.add_task(AIService.submission_generation_worker, job_id, request.submission_id)
    
    return JobResponse(job_id=job_id, message="Submission generation job queued successfully.")

@router.get("/admin/ai/status/{job_id}", response_model=JobStatusResponse)
async def admin_ai_status(job_id: str):
    """
    Polling endpoint used by the frontend to check whether the ElevenLabs/OpenAI job is complete.
    """
    status = AIService.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
        
    return JobStatusResponse(job_id=job_id, status=status)
