import json
import logging
import math
import os
import random
import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.llm import get_story_llm, generate_voice_elevenlabs, save_audio, ELEVENLABS_VOICES
from app.data import story as story_data
from app.model.story import (
    AssetReviewStatus,
    GenerationStatus,
    ImageSource,
    ModerationStatus,
    Story,
    StoryType,
    SubmissionMode,
)
from app.utils.media import get_mp3_duration

logger = logging.getLogger(__name__)

CANONICAL_GROWTH_AREAS = [
    "Fear & Freedom",
    "Self-Acceptance",
    "Forgiveness",
    "Letting Go",
    "Presence",
    "Self-Compassion",
    "Rebuilding",
    "Patience",
    "Love & Connection",
    "Purpose & Meaning",
]

CANONICAL_GROWTH_MAP = {g.lower(): g for g in CANONICAL_GROWTH_AREAS}
CANONICAL_GROWTH_MAP.update({
    "fear and freedom": "Fear & Freedom",
    "love and connection": "Love & Connection",
    "purpose and meaning": "Purpose & Meaning",
    "self acceptance": "Self-Acceptance",
    "self compassion": "Self-Compassion",
})

CANONICAL_LIFE_PHASES = [
    "Discovering",
    "Building",
    "Recalibrating",
    "Deepening",
    "Passing On",
]

CANONICAL_LIFE_PHASE_MAP = {lp.lower(): lp for lp in CANONICAL_LIFE_PHASES}
CANONICAL_LIFE_PHASE_MAP.update({
    "passing_on": "Passing On",
    "passing-on": "Passing On",
})

BULK_EXTRACTION_SYSTEM_PROMPT = """\
You are an expert editorial curator for an intimate storytelling platform.
Your task is to analyze a raw document containing one or more personal confessions, meditations, or transformative stories.

You must:
1. Identify each distinct story in the document (separated by headings, numbers, titles, lines, or narrative shifts).
2. For each identified story, extract and clean the full narrative text.
3. Classify and extract metadata (title, story type, author details, mood tags, canonical growth areas, life phase, hook, and tagline).

Strict Output Format:
Return ONLY a valid JSON object matching this exact schema:
{
  "stories": [
    {
      "title": "Clean Story Title",
      "story_type": "confession", // one of: "confession", "meditation", "transformation"
      "story_text": "The complete, unabridged narrative of this specific story...",
      "first_name": "Narrator name or pseudonym (e.g. 'Marcus', 'Elena', or 'Anonymous')",
      "age": 34, // integer or null
      "gender": "female", // "male", "female", "non-binary", or null
      "city": "City name or null",
      "country": "Country name or null",
      "occupation": "Occupation or null",
      "sexual_orientation": "Orientation or null",
      "growth_areas": ["Self-Acceptance", "Letting Go"], // 1 to 3 items STRICTLY from: ["Fear & Freedom", "Self-Acceptance", "Forgiveness", "Letting Go", "Presence", "Self-Compassion", "Rebuilding", "Patience", "Love & Connection", "Purpose & Meaning"]
      "life_phase": "Discovering", // ONE item STRICTLY from: ["Discovering", "Building", "Recalibrating", "Deepening", "Passing On"]
      "tags": ["vulnerability", "healing", "evening"], // 3 to 6 descriptive lowercase mood/theme tags
      "high_intensity": false, // true ONLY if explicitly adult/erotic content
      "hero_hook": "2 to 3 evocative sentences capturing the emotional turning point of the story.",
      "hero_tagline": "A short, poetic brushstroke phrase summarizing the theme."
    }
  ]
}

Rules:
- Do NOT fabricate or invent stories that do not exist in the document.
- Preserve the authentic author's voice and text in "story_text".
- If the document contains only one story, return an array of 1 story.
- If multiple stories exist, preserve each as a separate item in "stories".
- No markdown wrapping, no introductory or concluding text, just valid JSON.
"""


def _clean_json_response(raw: str) -> str:
    """Strips markdown code blocks, preamble, and postscript."""
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _normalize_story_item(item: Dict[str, Any], default_story_type: Optional[str] = None) -> Dict[str, Any]:
    """Ensures extracted fields conform to database schemas and canonical enums."""
    title = str(item.get("title") or "Untitled").strip()
    story_text = str(item.get("story_text") or "").strip()
    if not story_text:
        return {}

    # Story Type
    raw_type = str(item.get("story_type") or default_story_type or "confession").lower().strip()
    if "meditat" in raw_type:
        stype = "meditation"
    elif "transfor" in raw_type or "journey" in raw_type or "liberat" in raw_type:
        stype = "transformation"
    else:
        stype = "confession"

    # Normalize Growth Areas
    raw_growth = item.get("growth_areas") or []
    if isinstance(raw_growth, str):
        raw_growth = [g.strip() for g in raw_growth.split(",") if g.strip()]
    normalized_growth = []
    for g in raw_growth:
        g_clean = str(g).strip().lower()
        if g_clean in CANONICAL_GROWTH_MAP:
            normalized_growth.append(CANONICAL_GROWTH_MAP[g_clean])
        elif str(g).strip():
            normalized_growth.append(str(g).strip())
    # deduplicate
    seen = set()
    final_growth = []
    for g in normalized_growth:
        if g not in seen:
            seen.add(g)
            final_growth.append(g)

    # Normalize Life Phase
    raw_lp = str(item.get("life_phase") or "").strip().lower()
    final_life_phase = CANONICAL_LIFE_PHASE_MAP.get(raw_lp)
    if not final_life_phase and raw_lp:
        final_life_phase = str(item.get("life_phase")).strip()

    # Normalize Age
    age = item.get("age")
    try:
        age_int = int(age) if age is not None else None
    except (ValueError, TypeError):
        age_int = None

    # Tags
    raw_tags = item.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    tags = [str(t).strip().lower() for t in raw_tags if str(t).strip()][:6]

    return {
        "title": title,
        "story_type": stype,
        "story_text": story_text,
        "first_name": str(item.get("first_name") or "").strip() or None,
        "gender": str(item.get("gender") or "").strip().lower() or None,
        "age": age_int,
        "city": str(item.get("city") or "").strip() or None,
        "country": str(item.get("country") or "").strip() or None,
        "occupation": str(item.get("occupation") or "").strip() or None,
        "sexual_orientation": str(item.get("sexual_orientation") or "").strip() or None,
        "growth_areas": final_growth[:4],
        "life_phase": final_life_phase,
        "tags": tags,
        "high_intensity": bool(item.get("high_intensity", False)),
        "hero_hook": str(item.get("hero_hook") or "").strip() or None,
        "hero_tagline": str(item.get("hero_tagline") or "").strip() or None,
    }


def parse_and_split_document_text(
    raw_text: str,
    default_story_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Uses LLM to separate multiple stories and extract structured metadata for each.
    """
    text_content = (raw_text or "").strip()
    if not text_content:
        raise ValueError("Document contains no readable text.")

    # Approximate token estimation (1 token ≈ 4 characters).
    # If text is excessively long (> 45,000 chars), we can process in chunks.
    llm = get_story_llm(temperature=0.2, max_tokens=8192)

    prompt = (
        f"{BULK_EXTRACTION_SYSTEM_PROMPT}\n\n"
        f"--- DOCUMENT CONTENT START ---\n"
        f"{text_content}\n"
        f"--- DOCUMENT CONTENT END ---\n"
    )

    try:
        response = llm.invoke(prompt)
        content_str = response.content if hasattr(response, "content") else str(response)
        cleaned_json = _clean_json_response(content_str)
        data = json.loads(cleaned_json)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM JSON response for bulk extraction: %s", exc)
        # Attempt to find json substring inside content
        match = re.search(r"\{.*\}", content_str, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                raise ValueError("AI was unable to return properly formatted story data. Please check the document format.")
        else:
            raise ValueError("AI was unable to separate stories from the uploaded document.")
    except Exception as exc:
        logger.error("LLM invocation error during bulk story extraction: %s", exc)
        raise ValueError(f"AI story separation failed: {exc}")

    stories_raw = data.get("stories")
    if not stories_raw or not isinstance(stories_raw, list):
        raise ValueError("No stories were identified in the document.")

    normalized_stories = []
    for item in stories_raw:
        if isinstance(item, dict):
            norm = _normalize_story_item(item, default_story_type)
            if norm and norm.get("story_text"):
                normalized_stories.append(norm)

    if not normalized_stories:
        raise ValueError("No valid story content could be extracted from the document.")

    return normalized_stories


def bulk_audio_worker(job_id_str: str, story_db_id: str, text: str) -> None:
    """
    Background worker that generates narration audio with ElevenLabs for an ingested story.
    """
    bg_db = SessionLocal()
    try:
        story_row = bg_db.query(Story).filter(Story.id == story_db_id).first()
        if not story_row:
            return

        is_french = False
        french_indicators = [
            r'\bje\b', r'\bvous\b', r'\bavec\b', r'\bpour\b', r'\bdans\b',
            r'\bmais\b', r'\bune\b', r'\bqui\b', r'\bque\b', r'\best\b',
            r'\bde\b', r'\ble\b', r'\bla\b', r'\bet\b', r'\bun\b', r'\bdu\b'
        ]
        matches = sum(1 for pattern in french_indicators if re.search(pattern, text, re.IGNORECASE))
        if matches >= 3:
            is_french = True

        FEMALE_VOICES = ["Sophia", "Charlotte", "Victoria", "Anja", "Chapter1"]
        if story_row.gender == "female":
            new_voice_name = "Victoria" if is_french else random.choice(FEMALE_VOICES)
        else:
            new_voice_name = "Calen"

        story_row.voice_name = new_voice_name
        if new_voice_name in ELEVENLABS_VOICES:
            story_row.voice_id = ELEVENLABS_VOICES[new_voice_name]
        story_row.uses_custom_voice = False

        audio_bytes, alignment = generate_voice_elevenlabs(
            text=text,
            voice_id=new_voice_name,
            return_timestamps=True,
            story_type=story_row.story_type,
        )
        audio_path = save_audio(audio_bytes)
        story_row.alignment = alignment

        exact_duration = get_mp3_duration(audio_bytes)
        if exact_duration > 0.0:
            duration_secs = int(math.ceil(exact_duration))
        else:
            word_count = len(text.split())
            duration_secs = int((word_count / 150) * 60)

        story_row.audio_path = audio_path
        story_row.audio_duration_seconds = duration_secs
        story_row.voice_status = AssetReviewStatus.ready_for_review
        story_row.generation_status = GenerationStatus.completed
        bg_db.commit()
        logger.info(f"[Bulk Audio Job {job_id_str}] Generated narration with {new_voice_name}: {audio_path}")
    except Exception as exc:
        logger.error(f"[Bulk Audio Job {job_id_str}] Failed to generate audio: {exc}", exc_info=True)
        try:
            story_row = bg_db.query(Story).filter(Story.id == story_db_id).first()
            if story_row:
                story_row.voice_status = AssetReviewStatus.missing
                bg_db.commit()
        except Exception:
            pass
    finally:
        bg_db.close()


def ingest_bulk_stories(
    db: Session,
    stories_data: List[Dict[str, Any]],
    admin_id: Optional[str],
    background_tasks: BackgroundTasks,
    generate_covers: bool = True,
    generate_audio: bool = False,
) -> List[Dict[str, Any]]:
    """
    Inserts multiple extracted stories into the database and queues asset workers.
    """
    from app.api.v1.endpoints.admin.route_moderation import _regenerate_cover_worker

    created_stories = []

    for item in stories_data:
        job_id = str(uuid.uuid4())
        stype = StoryType(item.get("story_type", "confession"))

        story = story_data.create_story(
            db=db,
            story_type=stype,
            job_id=job_id,
            user_id=None,
            admin_id=admin_id,
            title=item.get("title"),
            first_name=item.get("first_name"),
            city=item.get("city"),
            country=item.get("country"),
            gender=item.get("gender"),
            sexual_orientation=item.get("sexual_orientation"),
            occupation=item.get("occupation"),
            age=item.get("age"),
            story_input=item.get("story_text"),
            submission_mode=SubmissionMode.studio,
            growth_areas=item.get("growth_areas") or [],
            life_phase=item.get("life_phase"),
            tags=item.get("tags") or [],
            high_intensity=bool(item.get("high_intensity", False)),
        )

        # Set content details
        story.story_text = item.get("story_text")
        story.hero_hook = item.get("hero_hook")
        story.hero_tagline = item.get("hero_tagline")
        story.moderation_status = ModerationStatus.pending
        story.content_status = AssetReviewStatus.ready_for_review
        story.generation_status = GenerationStatus.completed

        # Cover asset setup
        if generate_covers:
            story.cover_status = AssetReviewStatus.in_progress
            background_tasks.add_task(_regenerate_cover_worker, str(story.id))
        else:
            story.cover_status = AssetReviewStatus.missing

        # Audio asset setup
        if generate_audio:
            story.voice_status = AssetReviewStatus.in_progress
            background_tasks.add_task(bulk_audio_worker, job_id, str(story.id), story.story_text)
        else:
            story.voice_status = AssetReviewStatus.missing

        db.commit()
        db.refresh(story)

        created_stories.append({
            "id": str(story.id),
            "story_number": story.story_number,
            "title": story.title or "Untitled",
            "story_type": story.story_type.value,
            "cover_status": story.cover_status.value if story.cover_status else "missing",
            "voice_status": story.voice_status.value if story.voice_status else "missing",
            "content_status": story.content_status.value if story.content_status else "ready_for_review",
        })

    return created_stories
