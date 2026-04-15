"""
service_rag.py
RAG pipeline: embedding stories into Pinecone and querying for book recommendations.

Uses xAI embeddings via the OpenAI-compatible /v1/embeddings endpoint and
Grok LLM for synthesising book suggestions from retrieved story context.
"""
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pinecone import Pinecone, ServerlessSpec
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_story_llm
from app.model.story import Story, GenerationStatus, StoryType
from app.model.profile import UserProfile
from app.schemas.schema_rag import (
    BookRecommendation,
    BookRecommendationsResponse,
    StoryTypeFilter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "v1"                     # xAI embedding model name
EMBEDDING_DIMENSION = 2048                  # xAI default embedding dimension
PINECONE_METRIC = "cosine"
TOP_K = 5

# Fallback book pool — served when Pinecone returns no relevant results
FALLBACK_BOOKS: List[dict] = [
    {"title": "The Alchemist", "author": "Paulo Coelho",
     "reason": "A timeless fable about following your personal legend and discovering your true purpose."},
    {"title": "Man's Search for Meaning", "author": "Viktor E. Frankl",
     "reason": "A profound exploration of finding meaning even in the most challenging circumstances."},
    {"title": "The Power of Now", "author": "Eckhart Tolle",
     "reason": "A guide to spiritual enlightenment and living fully in the present moment."},
    {"title": "Atomic Habits", "author": "James Clear",
     "reason": "Practical strategies for building good habits and breaking bad ones."},
    {"title": "Untamed", "author": "Glennon Doyle",
     "reason": "An inspiring memoir about trusting yourself and pursuing your own path."},
    {"title": "Daring Greatly", "author": "Brené Brown",
     "reason": "How the courage to be vulnerable transforms the way we live, love, and lead."},
    {"title": "The Body Keeps the Score", "author": "Bessel van der Kolk",
     "reason": "Groundbreaking insights into how trauma affects the body and paths to recovery."},
    {"title": "Meditations", "author": "Marcus Aurelius",
     "reason": "Timeless stoic philosophy for inner peace and self-mastery."},
    {"title": "Big Magic", "author": "Elizabeth Gilbert",
     "reason": "Embracing creativity and living a life driven by curiosity over fear."},
    {"title": "When Things Fall Apart", "author": "Pema Chödrön",
     "reason": "Heart advice for difficult times rooted in Buddhist compassion practices."},
]


# ---------------------------------------------------------------------------
# Prompt templates for book recommendation synthesis
# ---------------------------------------------------------------------------
BOOK_REC_SYSTEM = """\
You are a world-class book recommendation expert for the Transform to Liberation platform.

Based on retrieved story contexts that resonate with this user's profile, recommend exactly 5 books.
Each recommendation must feel deeply personal to the user's life phase, priorities, and emotional landscape.

Return ONLY a valid JSON array with exactly 5 objects, each having:
- "title": the book title
- "author": the author name
- "reason": a 1-2 sentence explanation of why this book specifically resonates with the user

Do NOT include any text before or after the JSON array. No markdown, no code fences.
"""

BOOK_REC_HUMAN = """\
## User Profile
Life phase: {life_phase}
Location: {location}
Top priorities: {priorities}
Age: {age}
Gender: {gender}

## Stories That Resonate With This User
{story_context}

Based on the themes, emotions, and life situations reflected in these stories, recommend 5 books \
that would deeply resonate with this user right now.
"""


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _get_embeddings() -> OpenAIEmbeddings:
    """Returns an xAI-compatible embedding client via langchain_openai."""
    if not settings.XAI_API_KEY:
        raise ValueError("XAI_API_KEY is missing. Add it to your .env file.")
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=settings.XAI_API_KEY,
        openai_api_base="https://api.x.ai/v1",
    )


def _get_pinecone_index():
    """
    Returns a Pinecone Index object. Auto-creates the index if it doesn't exist.
    """
    if not settings.PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY is missing. Add it to your .env file.")

    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index_name = settings.PINECONE_INDEX_NAME

    # Auto-create if absent
    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        logger.info(f"Creating Pinecone index '{index_name}' (dim={EMBEDDING_DIMENSION})...")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIMENSION,
            metric=PINECONE_METRIC,
            spec=ServerlessSpec(
                cloud="aws",
                region=settings.PINECONE_ENVIRONMENT or "us-east-1",
            ),
        )
        logger.info(f"Pinecone index '{index_name}' created successfully.")

    return pc.Index(index_name)


# ---------------------------------------------------------------------------
# Document building
# ---------------------------------------------------------------------------

def _build_document_text(story: Story) -> str:
    """Compose a rich text blob for embedding from a Story row."""
    parts = []
    if story.story_type:
        parts.append(f"Story Type: {story.story_type.value}")
    if story.title:
        parts.append(f"Title: {story.title}")
    if story.story_text:
        parts.append(f"Story: {story.story_text}")
    if story.life_phase:
        parts.append(f"Life Phase: {story.life_phase}")
    if story.emotional_context:
        parts.append(f"Emotional Context: {json.dumps(story.emotional_context)}")
    if story.deepest_desire_fear:
        parts.append(f"Deepest Desire/Fear: {story.deepest_desire_fear}")
    return "\n".join(parts)


def _build_metadata(story: Story) -> dict:
    """Pinecone vector metadata — used for filtering and display."""
    return {
        "story_id": str(story.id),
        "story_type": story.story_type.value if story.story_type else "",
        "title": story.title or "",
        "life_phase": story.life_phase or "",
        "user_id": str(story.user_id) if story.user_id else "",
        "created_at": story.created_at.isoformat() if story.created_at else "",
    }


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class RAGService:

    @staticmethod
    def ingest_all_stories(db: Session) -> int:
        """
        Full re-index: embed all completed stories and upsert into Pinecone.
        Returns the number of stories indexed.
        """
        stories = (
            db.query(Story)
            .filter(Story.generation_status == GenerationStatus.completed)
            .filter(Story.story_text.isnot(None))
            .all()
        )

        if not stories:
            logger.info("No completed stories to index.")
            return 0

        return RAGService._embed_and_upsert(stories)

    @staticmethod
    def ingest_new_stories(db: Session, since: Optional[datetime] = None) -> int:
        """
        Incremental index: only stories created after `since`.
        Defaults to last 24 hours when since is None.
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)

        stories = (
            db.query(Story)
            .filter(Story.generation_status == GenerationStatus.completed)
            .filter(Story.story_text.isnot(None))
            .filter(Story.created_at >= since)
            .all()
        )

        if not stories:
            logger.info(f"No new completed stories since {since.isoformat()}.")
            return 0

        return RAGService._embed_and_upsert(stories)

    # --- internal batch embed + upsert ------------------------------------

    @staticmethod
    def _embed_and_upsert(stories: list[Story]) -> int:
        """Embed a batch of stories and upsert into Pinecone. Returns count."""
        embeddings_client = _get_embeddings()
        index = _get_pinecone_index()

        texts = [_build_document_text(s) for s in stories]
        vectors = embeddings_client.embed_documents(texts)

        # Build upsert payload — Pinecone accepts list of (id, values, metadata)
        upsert_data = []
        for story, vec in zip(stories, vectors):
            upsert_data.append({
                "id": str(story.id),
                "values": vec,
                "metadata": _build_metadata(story),
            })

        # Upsert in batches of 100 (Pinecone limit)
        batch_size = 100
        for i in range(0, len(upsert_data), batch_size):
            batch = upsert_data[i : i + batch_size]
            index.upsert(vectors=batch)

        logger.info(f"Upserted {len(stories)} stories into Pinecone.")
        return len(stories)

    # -----------------------------------------------------------------------
    # Query / Recommendation
    # -----------------------------------------------------------------------

    @staticmethod
    def get_book_recommendations(
        db: Session,
        user_id: str,
        story_type: StoryTypeFilter = StoryTypeFilter.all,
    ) -> BookRecommendationsResponse:
        """
        1. Build a query from the user's UserProfile.
        2. Search Pinecone for top-K similar story documents (optionally filtered by type).
        3. Use Grok LLM to synthesise book recommendations.
        4. If Pinecone returns nothing, fall back to random curated books.
        """
        # --- Fetch user profile -----------------------------------------------
        profile: Optional[UserProfile] = (
            db.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )

        life_phase = profile.life_phase if profile else "unknown"
        location = (
            f"{profile.country or ''}/{profile.city or ''}".strip("/")
            if profile
            else "unknown"
        )
        age = str(profile.age) if profile and profile.age else "unknown"
        gender = profile.gender if profile and profile.gender else "unknown"

        # Build slider priority summary (top 3 by value)
        priorities = "unknown"
        if profile:
            slider_map = {
                "Desire & Relationship": profile.slider_desire_relationship,
                "Life Purpose": profile.slider_life_purpose,
                "Career & Money": profile.slider_career_money,
                "True Self": profile.slider_true_self,
                "Security & Energy": profile.slider_security_energy,
                "Freedom": profile.slider_free_freedom,
                "Health & Body": profile.slider_health_body,
                "Enlightenment": profile.slider_enlightenment,
                "Social & Relational": profile.slider_social_relational,
            }
            ranked = sorted(
                ((k, v) for k, v in slider_map.items() if v is not None),
                key=lambda x: x[1],
                reverse=True,
            )
            if ranked:
                priorities = ", ".join(
                    f"{name} ({val}/10)" for name, val in ranked[:3]
                )

        # --- Build query text for Pinecone ------------------------------------
        query_text = (
            f"Life phase: {life_phase}\n"
            f"Location: {location}\n"
            f"Key priorities: {priorities}\n"
            f"Age: {age}, Gender: {gender}"
        )

        # --- Vector search ----------------------------------------------------
        try:
            embeddings_client = _get_embeddings()
            index = _get_pinecone_index()

            query_vector = embeddings_client.embed_query(query_text)

            # Optional story_type filter
            pinecone_filter = None
            if story_type != StoryTypeFilter.all:
                pinecone_filter = {"story_type": {"$eq": story_type.value}}

            results = index.query(
                vector=query_vector,
                top_k=TOP_K,
                include_metadata=True,
                filter=pinecone_filter,
            )

            matches = results.get("matches", [])
        except Exception as e:
            logger.error(f"Pinecone query failed: {e}", exc_info=True)
            matches = []

        # --- Fallback: random books -------------------------------------------
        if not matches:
            logger.info(f"No Pinecone matches for user {user_id}. Returning random books.")
            sample = random.sample(FALLBACK_BOOKS, min(5, len(FALLBACK_BOOKS)))
            return BookRecommendationsResponse(
                recommendations=[BookRecommendation(**b) for b in sample],
                source="random",
            )

        # --- Build story context for LLM -------------------------------------
        story_snippets = []
        for i, match in enumerate(matches, 1):
            meta = match.get("metadata", {})
            snippet = (
                f"{i}. [{meta.get('story_type', 'story').title()}] "
                f"\"{meta.get('title', 'Untitled')}\"\n"
                f"   Life phase: {meta.get('life_phase', 'N/A')}\n"
                f"   Score: {match.get('score', 0):.3f}"
            )
            story_snippets.append(snippet)

        story_context = "\n".join(story_snippets)

        # --- LLM synthesis ----------------------------------------------------
        try:
            llm = get_story_llm(temperature=0.7)

            chat_prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(BOOK_REC_SYSTEM),
                HumanMessagePromptTemplate.from_template(BOOK_REC_HUMAN),
            ])

            formatted = chat_prompt.format_prompt(
                life_phase=life_phase,
                location=location,
                priorities=priorities,
                age=age,
                gender=gender,
                story_context=story_context,
            ).to_messages()

            response = llm.invoke(formatted)
            raw = response.content.strip()

            # Strip markdown code fences if the model wraps anyway
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

            books_data = json.loads(raw)
            recommendations = [BookRecommendation(**b) for b in books_data[:5]]

            return BookRecommendationsResponse(
                recommendations=recommendations,
                source="rag",
            )

        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}", exc_info=True)
            # Graceful degradation — return random books
            sample = random.sample(FALLBACK_BOOKS, min(5, len(FALLBACK_BOOKS)))
            return BookRecommendationsResponse(
                recommendations=[BookRecommendation(**b) for b in sample],
                source="random",
            )
