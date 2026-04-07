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
    save_audio_locally,
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
        Business logic: Connect to Pinecone and embed the query using OpenAI.

        # --- EXTERNAL API / DB INTEGRATION COMMENTS ---
        # 1. Embedding Call: Use text-embedding-3-small to embed the string
        #    from langchain_openai import OpenAIEmbeddings
        #    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        #    query_vector = embeddings.embed_query(query)
        #
        # 2. Vector DB Query: Connect to Pinecone or pgvector
        #    index = pinecone.Index("transform-to-liberation")
        #    response = index.query(vector=query_vector, top_k=5, include_metadata=True)
        #
        # 3. Process Results:
        #    track_ids = [match['metadata']['track_id'] for match in response['matches']]
        """
        # Mocked semantic search return
        return SearchResult(
            track_ids=["trk_452", "trk_189", "trk_093", "trk_332", "trk_111"]
        )

    # --- Resonance Question -------------------------------------------------

    @staticmethod
    def generate_resonance_question(request: ResonanceRequest) -> ResonanceResponse:
        """
        Generates a deeply reflective journaling question using SuperGrok.
        Prompt template lives in app/utils/prompts.py.
        Temperature is loaded from LLM_TEMPERATURE_RESONANCE in settings.
        """
        llm = get_story_llm(temperature=None)

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(RESONANCE_SYSTEM_TEMPLATE),
            HumanMessagePromptTemplate.from_template(RESONANCE_HUMAN_TEMPLATE),
        ])

        sliders_str = ", ".join(
            [f"{k.replace('_', ' ')}: {v}/10" for k, v in request.sliders.items()]
        )
        formatted_messages = chat_prompt.format_prompt(
            track_id=request.track_id,
            sliders=sliders_str,
        ).to_messages()

        response = llm.invoke(formatted_messages)
        return ResonanceResponse(journaling_question=response.content.strip())

    # --- Story Generation ---------------------------------------------------

    @staticmethod
    def generate_story(request: StoryGenerateRequest) -> str:
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
        return response.content.strip()

    @staticmethod
    def generate_and_voice_story(request: StoryGenerateRequest) -> Tuple[str, str]:
        """
        Generates a story with SuperGrok, then converts it to audio via
        ElevenLabs and saves it locally. Returns (story_text, audio_path).
        """
        story_text = AIService.generate_story(request)
        audio_bytes = generate_voice_elevenlabs(text=story_text)
        audio_path = save_audio_locally(audio_bytes)
        return story_text, audio_path

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

            story_text, audio_path = AIService.generate_and_voice_story(request)

            story_data.complete_story(
                db=db,
                story=story_row,
                story_text=story_text,
                audio_path=audio_path,
            )
            logger.info(f"[Job {job_id}] Completed. Audio saved: {audio_path}")

        except Exception as e:
            logger.error(f"[Job {job_id}] FAILED: {e}", exc_info=True)
            try:
                story_row = db.query(StoryModel).filter(
                    StoryModel.id == story_db_id
                ).first()
                if story_row:
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

        # --- EXTERNAL API / LOGIC COMMENTS ---
        # 1. Build a StoryGenerateRequest from the topic and story_type
        # 2. Call AIService.generate_and_voice_story(request)
        # 3. Call StoryService.complete_story() to save text + audio_path
        #    When S3 is ready: swap save_audio_locally() for S3 upload in llm.py
        """
        from app.core.db import SessionLocal
        from app.model.story import Story as StoryModel

        db = SessionLocal()
        try:
            story_row = db.query(StoryModel).filter(
                StoryModel.job_id == job_id
            ).first()
            # TODO: implement actual generation and call story_data.complete_story()
            logger.info(f"[Bulk Job {job_id}] Worker placeholder — implement generation here.")
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
        Returns a job_id stored in stories.job_id.
        """
        job_id = str(uuid.uuid4())
        logger.info(f"[Submission Job {job_id}] Queued for submission {submission_id}.")
        return job_id

    @staticmethod
    def submission_generation_worker(job_id: str, submission_id: str):
        """
        Processes a user submission: analyse responses, generate a story.
        TODO: implement full logic using app.data.story and AIService.generate_story()
        """
        logger.info(f"[Submission Job {job_id}] Processing submission {submission_id}.")

    # --- Job status — reads directly from PostgreSQL ------------------------

    @staticmethod
    def get_job_status(job_id: str) -> Optional[dict]:
        """
        Fetches job status directly from the `stories` table by job_id.
        Returns a dict with 'status' and 'audio_path', or None if not found.
        """
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            story = story_data.get_story_by_job_id(db=db, job_id=job_id)
            if not story:
                return None
            return {
                "status": story.generation_status.value,
                "audio_path": story.audio_path,
                "story_text": story.story_text,
            }
        finally:
            db.close()
