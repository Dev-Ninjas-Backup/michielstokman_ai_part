from pydantic import BaseModel, Field
from typing import Dict, List

class SearchResult(BaseModel):
    track_ids: List[str] = Field(..., description="List of the top 5 relevant track IDs")

class ResonanceRequest(BaseModel):
    track_id: str = Field(..., description="The ID of the track the user is associating with")
    sliders: Dict[str, int] = Field(
        ..., 
        description="A dictionary of emotional sliders, e.g. {'tension': 80, 'openness': 30}"
    )

class ResonanceResponse(BaseModel):
    journaling_question: str = Field(..., description="The generated journaling question")

class BulkGenerateRequest(BaseModel):
    topic: str = Field(..., description="The main topic for the generated content")
    format: str = Field(..., description="The format of the content, e.g. 'audio_script'")

class SubmissionGenerateRequest(BaseModel):
    submission_id: str = Field(..., description="The unique ID of the user submission")

class JobResponse(BaseModel):
    job_id: str = Field(..., description="The unique identifier for the async job")
    message: str = Field(..., description="Confirmation message")

class JobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(..., description="Current status of the job: 'processing', 'completed', 'failed'")
