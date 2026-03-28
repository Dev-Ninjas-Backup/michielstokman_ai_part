import uuid
from typing import Dict, Optional
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

from app.schemas.schema_ai import (
    SearchResult,
    ResonanceRequest,
    ResonanceResponse,
)
from app.utils.llm import get_story_llm

# Mock in-memory database or Redis layer for tracking async job statuses
fake_job_tracker: Dict[str, str] = {}

class AIService:
    @staticmethod
    def search_tracks(query: str) -> SearchResult:
        """
        Business logic: Connect to Pinecone and embed the query using OpenAI.
        
        # --- EXTERNAL API / DB INTEGRATION COMMENTS ---
        # 1. EMbedding Call: Use text-embedding-3-small to embed the string
        #    from langchain_openai import OpenAIEmbeddings
        #    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        #    query_vector = embeddings.embed_query(query)
        #
        # 2. Vector DB Query: Connect to Pinecone or pgvector
        #    E.g. (Pinecone natively):
        #    index = pinecone.Index("transform-to-liberation")
        #    response = index.query(vector=query_vector, top_k=5, include_metadata=True)
        #
        # 3. Process Results:
        #    track_ids = [match['metadata']['track_id'] for match in response['matches']]
        """
        # Mocking the semantic search return
        return SearchResult(track_ids=["trk_452", "trk_189", "trk_093", "trk_332", "trk_111"])

    @staticmethod
    def generate_resonance_question(request: ResonanceRequest) -> ResonanceResponse:
        """
        Business logic: Generates the journaling question using ChatOpenAI.
        """
        # Initialize standard LLM wrapper (requires OPENAI_API_KEY environment variable)
        llm = get_story_llm(temperature=0.7)
        
        system_template = (
            "You are a compassionate emotional wellness guide working for 'Transform to Liberation'. "
            "A user has just completed a listening session for track ID {track_id}. "
            "They set their emotional sliders to the following values: {sliders}. "
            "Based on these emotions, generate a single, deeply reflective journaling question "
            "that encourages them to explore their feelings without judgment. "
            "Return absolutely nothing but the question."
        )
        system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)
        
        human_template = "Generate the journaling question."
        human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)
        
        chat_prompt = ChatPromptTemplate.from_messages([
            system_message_prompt, 
            human_message_prompt
        ])
        
        sliders_str = ", ".join([f"{k}: {v}" for k, v in request.sliders.items()])
        formatted_messages = chat_prompt.format_prompt(
            track_id=request.track_id, 
            sliders=sliders_str
        ).to_messages()
        
        # Execute actual inference against OpenAI
        response = llm.invoke(formatted_messages)
        
        return ResonanceResponse(journaling_question=response.content.strip())

    @staticmethod
    def initiate_bulk_generation(topic: str, format: str) -> str:
        """Prepares a bulk generation job and registers it."""
        job_id = str(uuid.uuid4())
        fake_job_tracker[job_id] = "processing"
        return job_id

    @staticmethod
    async def bulk_generation_worker(job_id: str, topic: str, format: str):
        """
        Background worker simulating a complex AI workflow.
        """
        try:
            # --- EXTERNAL API / LOGIC COMMENTS ---
            # 1. Grok Story Generation Logic:
            #    from app.utils.llm import get_story_llm
            #    grok_llm = get_story_llm(model_name="grok-beta")
            #    script = grok_llm.invoke(f"Write a {format} about {topic}...")
            #
            # 2. ElevenLabs TTS logic:
            #    from app.utils.voice import generate_voice_elevenlabs
            #    audio_bytes = generate_voice_elevenlabs(
            #        text=script.content, 
            #        voice_id="your-voice-id"
            #    )
            # 
            # 3. Storage layer logic:
            #    Save raw bytes from ElevenLabs to AWS S3 / Google Cloud Storage.
            #    Save the S3 URI to the primary PostGres DB via the `models` layer.
            
            # Simulate completion
            fake_job_tracker[job_id] = "completed"
        except Exception:
            fake_job_tracker[job_id] = "failed"

    @staticmethod
    def initiate_submission_generation(submission_id: str) -> str:
        """Registers a user submission background generation task."""
        job_id = str(uuid.uuid4())
        fake_job_tracker[job_id] = "processing"
        return job_id

    @staticmethod
    async def submission_generation_worker(job_id: str, submission_id: str):
        """Processes the submission and updates generation state."""
        try:
            # Process submission via Langchain, e.g. analyze their text responses
            fake_job_tracker[job_id] = "completed"
        except Exception:
            fake_job_tracker[job_id] = "failed"

    @staticmethod
    def get_job_status(job_id: str) -> Optional[str]:
        """Fetches the state of an ongoing Async job."""
        return fake_job_tracker.get(job_id)
