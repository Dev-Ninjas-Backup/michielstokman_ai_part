"""
service_ai.py
Business logic for AI story generation (SuperGrok) and TTS (ElevenLabs).
All prompt templates and persona definitions live in app/utils/prompts.py.

Job status is tracked directly in the `stories` PostgreSQL table via
Story.generation_status and Story.job_id — no separate in-memory store needed.
"""
import uuid
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

from app.schemas.schema_ai import (
    SearchResult,
    ResonanceRequest,
    ResonanceResponse,
    StoryGenerateRequest,
)
from app.core.llm import (
    get_story_llm,
    generate_voice_elevenlabs,
    save_audio,
)
import app.data.story as story_data
from app.utils.prompts import (
    RESONANCE_SYSTEM_TEMPLATE,
    RESONANCE_HUMAN_TEMPLATE,
    STORY_HUMAN_TEMPLATE,
    build_story_system_template,
    build_user_context,
)


# ---------------------------------------------------------------------------
# Core AI service
# ---------------------------------------------------------------------------

class AIService:

    # --- Track Search -------------------------------------------------------

    @staticmethod
    def search_tracks(query: str) -> SearchResult:
        """
        Business logic: Connect to Pinecone and embed the query using xAI.
        Retrieves the top 5 most relevant liberation definitions (tracks).
        """
        from app.services.service_rag import _get_embeddings, _get_pinecone_index
        
        try:
            embeddings_client = _get_embeddings()
            index = _get_pinecone_index()

            # Embed the natural language query
            query_vector = embeddings_client.embed_query(query)

            # Query Pinecone for 'track' doc_types
            response = index.query(
                vector=query_vector,
                top_k=5,
                include_metadata=True,
                filter={"doc_type": {"$eq": "track"}}
            )

            # Extract track_ids (journey_codes or IDs) from metadata
            # The frontend expects strings, we use the journey_code for better readability if available, 
            # or the UUID string.
            track_ids = []
            for match in response.get("matches", []):
                meta = match.get("metadata", {})
                # Use journey_code if present, else fallback to track_id (UUID)
                t_id = meta.get("journey_code") or meta.get("track_id")
                if t_id:
                    track_ids.append(t_id)

            return SearchResult(track_ids=track_ids)

        except Exception as e:
            logger.error(f"Track search failed: {e}", exc_info=True)
            # Fallback to empty list or some default tracks if needed
            return SearchResult(track_ids=[])

    # --- Resonance Question -------------------------------------------------

    @staticmethod
    def generate_resonance_question(request: ResonanceRequest) -> ResonanceResponse:
        """
        Generates a deeply reflective journaling question using SuperGrok.
        Prompt template lives in app/utils/prompts.py.
        Now incorporates resonance_tags and feedback_text from Figma designs.
        """
        llm = get_story_llm(temperature=None)

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(RESONANCE_SYSTEM_TEMPLATE),
            HumanMessagePromptTemplate.from_template(RESONANCE_HUMAN_TEMPLATE),
        ])

        from app.utils.messages import AI_FALLBACK_FEEDBACK
        formatted_messages = chat_prompt.format_prompt(
            touch_score=request.touch_score,
            resonance_tags=", ".join(request.resonance_tags) if request.resonance_tags else "None",
            feedback_text=request.feedback_text or AI_FALLBACK_FEEDBACK,
        ).to_messages()

        response = llm.invoke(formatted_messages)
        return ResonanceResponse(journaling_question=response.content.strip())

    # --- Story Generation ---------------------------------------------------

    @staticmethod
    def generate_story(request: StoryGenerateRequest) -> Tuple[Optional[str], str]:
        """
        Generates a personalised Confession, Meditation, or Transformation
        using SuperGrok. Prompt templates live in app/utils/prompts.py.
        Temperature is loaded from LLM_TEMPERATURE_STORY in settings.
        """
        llm = get_story_llm()

        system_template = build_story_system_template(request.story_type)
        user_context = build_user_context(request)

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template(STORY_HUMAN_TEMPLATE),
        ])

        formatted_messages = chat_prompt.format_prompt(
            user_context=user_context,
            story_type=request.story_type.value,
        ).to_messages()

        response = llm.invoke(formatted_messages)
        content = response.content.strip()
        
        title = None
        story_text = content
        if "TITLE:" in content and "STORY:" in content:
            parts = content.split("STORY:", 1)
            title_part = parts[0].replace("TITLE:", "").strip()
            if title_part:
                title = title_part
            story_text = parts[1].strip()
            
        return title, story_text

    @staticmethod
    def generate_and_voice_story(request: StoryGenerateRequest) -> Tuple[Optional[str], str, str]:
        """
        Generates a story with SuperGrok, then converts it to audio via
        ElevenLabs and saves it locally. Returns (title, story_text, audio_path).
        """
        title, story_text = AIService.generate_story(request)
        audio_bytes = generate_voice_elevenlabs(text=story_text)
        audio_path = save_audio(audio_bytes)
        return title, story_text, audio_path

    # --- Background worker — story generation --------------------------------

    @staticmethod
    def story_generation_worker(
        job_id: str,
        request: StoryGenerateRequest,
        story_db_id: str,
    ):
        """
        Background task: SuperGrok generation + ElevenLabs TTS.
        All state (processing → completed / failed) is written directly to
        the `stories` PostgreSQL table — no separate in-memory store.

        IMPORTANT: Creates its own DB session. FastAPI closes the request
        session before background tasks run, so passing db from the route
        causes a silent 'Session already closed' crash.
        """
        from app.core.db import SessionLocal
        from app.model.story import Story as StoryModel

        db = SessionLocal()
        try:
            story_row = db.query(StoryModel).filter(
                StoryModel.id == story_db_id
            ).first()

            title, story_text, audio_path = AIService.generate_and_voice_story(request)

            story_data.complete_story(
                db=db,
                story=story_row,
                story_text=story_text,
                title=title,
                audio_path=audio_path,
            )
            
            # Simple duration estimation (150 wpm) and default voice lookup
            from app.core.config import settings
            from app.data import cover_image as cover_data
            from app.model.cover_image import CoverImageType

            story_row.voice_name = settings.ELEVENLABS_VOICE_ID
            word_count = len(story_text.split()) if story_text else 0
            story_row.audio_duration_seconds = int((word_count / 150) * 60)

            # Auto-assign cover image from admin uploads if not already set
            if not story_row.cover_image_url:
                c_type = CoverImageType(story_row.story_type.value)
                story_row.cover_image_url = cover_data.get_latest_active_image_url(db, c_type)

            db.commit()
            
            logger.info(f"[Job {job_id}] Completed. Audio saved: {audio_path}")

        except Exception as e:
            logger.error(f"[Job {job_id}] FAILED: {e}", exc_info=True)
            try:
                story_row = db.query(StoryModel).filter(
                    StoryModel.id == story_db_id
                ).first()
                if story_row:
                    story_row.title = f"API ERROR: {str(e)}"
                    story_data.fail_story(db=db, story=story_row)
            except Exception:
                pass
        finally:
            db.close()

    # --- Background worker — admin bulk generation ---------------------------

    @staticmethod
    def initiate_bulk_generation(topic: str, story_type: str, format: str) -> str:
        """
        Creates a Story row in 'processing' state for a bulk admin job.
        Returns a job_id that is stored in stories.job_id.
        """
        from app.core.db import SessionLocal
        from app.model.story import StoryType as StoryTypeEnum

        job_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            story_data.create_story(
                db=db,
                story_type=StoryTypeEnum(story_type),
                job_id=job_id,
                admin_id=None,
            )
        finally:
            db.close()
        return job_id

    @staticmethod
    def bulk_generation_worker(job_id: str, topic: str, story_type: str, format: str):
        """
        Background worker for admin bulk story generation.
        """
        from app.core.db import SessionLocal
        from app.model.story import Story as StoryModel

        db = SessionLocal()
        try:
            story_row = db.query(StoryModel).filter(
                StoryModel.job_id == job_id
            ).first()

            if not story_row:
                logger.error(f"[Bulk Job {job_id}] Story row not found in database.")
                return

            logger.info(f"[Bulk Job {job_id}] Starting generation for topic: {topic}")

            # 1. Build a StoryGenerateRequest from the topic and story_type
            from app.schemas.schema_ai import StoryGenerateRequest, StoryType
            
            request = StoryGenerateRequest(
                story_type=StoryType(story_type),
                topic=topic,
                specific_trigger=topic, # Use topic as the specific trigger for the prompt
                duration=5,
                parameters={}
            )

            # 2. Call AIService.generate_and_voice_story(request)
            title, story_text, audio_path = AIService.generate_and_voice_story(request)

            # 3. Call story_data.complete_story() to save text + audio_path
            story_data.complete_story(
                db=db,
                story=story_row,
                story_text=story_text,
                title=title,
                audio_path=audio_path,
            )
            
            # Auto-assign cover image from admin uploads if not already set
            from app.data import cover_image as cover_data
            from app.model.cover_image import CoverImageType
            if not story_row.cover_image_url:
                c_type = CoverImageType(story_row.story_type.value)
                story_row.cover_image_url = cover_data.get_latest_active_image_url(db, c_type)

            db.commit()
            
        except Exception as e:
            logger.error(f"[Bulk Job {job_id}] FAILED: {e}", exc_info=True)
            try:
                if story_row:
                    story_data.fail_story(db=db, story=story_row)
            except Exception:
                pass
        finally:
            db.close()

    # --- Submission generation -----------------------------------------------

    @staticmethod
    def initiate_submission_generation(submission_id: str) -> str:
        """
        Registers a user submission background generation task.
        Returns a job_id stored in liberation_definitions.job_id.
        """
        from app.core.db import SessionLocal
        from app.model.liberation import LiberationDefinition
        
        job_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            definition = db.query(LiberationDefinition).filter(LiberationDefinition.id == submission_id).first()
            if definition:
                definition.job_id = job_id
                definition.generation_status = "processing"
                db.commit()
                logger.info(f"[Submission Job {job_id}] Queued for LiberationDefinition {submission_id}.")
            else:
                logger.error(f"Submission {submission_id} not found.")
        finally:
            db.close()
            
        return job_id

    @staticmethod
    def submission_generation_worker(job_id: str, submission_id: str):
        """
        Processes a user submission: generates the day-by-day curriculum for a LiberationDefinition.
        """
        from app.core.db import SessionLocal
        from app.model.liberation import LiberationDefinition, LiberationDayDefinition
        from app.core.llm import get_story_llm
        import json
        
        db = SessionLocal()
        try:
            definition = db.query(LiberationDefinition).filter(LiberationDefinition.job_id == job_id).first()
            if not definition:
                logger.error(f"[Submission Job {job_id}] LiberationDefinition not found.")
                return
                
            logger.info(f"[Submission Job {job_id}] Generating {definition.total_days} days for: {definition.title}")
            
            # Generate the curriculum
            llm = get_story_llm()
            prompt = f'''
You are an expert curriculum designer for a mental health and meditation app.
A user has requested a {definition.total_days}-day journey.
Title: {definition.title}
Description: {definition.description}

Generate exactly {definition.total_days} daily themes for this journey.
Return the result strictly as a JSON array of objects. Do not include markdown formatting or extra text.
Each object must have "day_number" (integer) and "day_theme" (string).

Example:
[
  {{"day_number": 1, "day_theme": "Awakening to the Present"}},
  {{"day_number": 2, "day_theme": "Accepting the Shadows"}}
]
'''
            response = llm.invoke(prompt)
            response_text = response.content
            
            # Clean JSON if wrapped in markdown
            if response_text.startswith("```json"):
                response_text = response_text.strip("```json").strip("```").strip()
            elif response_text.startswith("```"):
                response_text = response_text.strip("```").strip()
            
            days_data = json.loads(response_text)
            
            # Delete existing days if any
            db.query(LiberationDayDefinition).filter(LiberationDayDefinition.definition_id == definition.id).delete()
            
            # Insert new days
            for day_data in days_data:
                day_def = LiberationDayDefinition(
                    definition_id=definition.id,
                    day_number=day_data.get("day_number"),
                    day_theme=day_data.get("day_theme")
                )
                db.add(day_def)
                
            definition.generation_status = "completed"
            db.commit()
            logger.info(f"[Submission Job {job_id}] Successfully generated {len(days_data)} days.")
            
        except Exception as e:
            logger.error(f"[Submission Job {job_id}] FAILED: {e}", exc_info=True)
            try:
                definition = db.query(LiberationDefinition).filter(LiberationDefinition.job_id == job_id).first()
                if definition:
                    definition.generation_status = "failed"
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    # --- Job status — reads directly from PostgreSQL ------------------------

    @staticmethod
    def get_job_status(job_id: str) -> Optional[dict]:
        """
        Fetches job status by checking the `stories` table, then the `liberation_definitions` table.
        Returns a dict with 'status' and 'audio_path', or None if not found.
        """
        from app.core.db import SessionLocal
        from app.model.liberation import LiberationDefinition

        db = SessionLocal()
        try:
            # 1. Check Stories
            story = story_data.get_story_by_job_id(db=db, job_id=job_id)
            if story:
                return {
                    "status": story.generation_status.value if hasattr(story.generation_status, 'value') else story.generation_status,
                    "title": story.title,
                    "audio_path": story.audio_path,
                    "story_text": story.story_text,
                }
            
            # 2. Check Liberation Definitions
            definition = db.query(LiberationDefinition).filter(LiberationDefinition.job_id == job_id).first()
            if definition:
                return {
                    "status": definition.generation_status,
                    "title": definition.title,
                    "audio_path": None,
                    "story_text": f"Liberation Journey Blueprint with {definition.total_days} days."
                }
                
            return None
        finally:
            db.close()
