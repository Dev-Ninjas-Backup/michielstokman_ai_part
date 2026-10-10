"""
service_ai.py
Business logic for AI story generation (SuperGrok) and TTS (ElevenLabs).
All prompt templates and persona definitions live in app/utils/prompts.py.

Job status is tracked directly in the `stories` PostgreSQL table via
Story.generation_status and Story.job_id — no separate in-memory store needed.
"""
import uuid
import logging
import re
from typing import Optional, Tuple, Dict, Any
import json

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, SystemMessage
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
    StoryType,
)
from app.core.llm import (
    get_story_llm,
    generate_voice_elevenlabs,
    save_audio,
)
from app.core.config import settings
import app.data.story as story_data
from app.utils.prompts import (
    RESONANCE_SYSTEM_TEMPLATE,
    RESONANCE_HUMAN_TEMPLATE,
    STORY_HUMAN_TEMPLATE,
    HERO_HOOK_SYSTEM,
    HERO_HOOK_HUMAN,
    HERO_TAGLINE_SYSTEM,
    HERO_TAGLINE_HUMAN,
    EDITORIAL_MOODS_SYSTEM,
    EDITORIAL_MOODS_HUMAN,
    EDITORIAL_BRIEF_SYSTEM,
    EDITORIAL_BRIEF_HUMAN,
    build_story_system_template,
    build_user_context,
    cover_identity_template_vars,
)
from app.utils.text import build_excerpt


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
    def select_voice_by_gender(gender: Optional[str], text: Optional[str] = None) -> str:
        """
        Currates premium voice lists to match the narrator/user's gender and story language.
        """
        import random
        import re
        from app.core.llm import ELEVENLABS_VOICES

        # Simple French detection
        is_french = False
        if text:
            french_indicators = [
                r'\bje\b', r'\bvous\b', r'\bavec\b', r'\bpour\b', r'\bdans\b', 
                r'\bmais\b', r'\bune\b', r'\bqui\b', r'\bque\b', r'\best\b', 
                r'\bde\b', r'\ble\b', r'\bla\b', r'\bet\b', r'\bun\b', r'\bdu\b'
            ]
            matches = sum(1 for pattern in french_indicators if re.search(pattern, text, re.IGNORECASE))
            if matches >= 3:
                is_french = True

        if is_french:
            FEMALE_VOICES = ["Victoria"]
            MALE_VOICES = ["Calen"]
        else:
            FEMALE_VOICES = ["Sophia", "Charlotte", "Anja", "Chapter1"]
            MALE_VOICES = ["Calen"]

        gender_lower = (gender or "").lower()
        if "female" in gender_lower or "woman" in gender_lower:
            return random.choice(FEMALE_VOICES)
        elif "male" in gender_lower or "man" in gender_lower:
            return random.choice(MALE_VOICES)
        else:
            # Empty / unspecified gender: mixed pool. Independent of story
            # PERSPECTIVE, which is now unspecified instead of default-female.
            all_options = FEMALE_VOICES + MALE_VOICES
            return random.choice(all_options)

    @staticmethod
    def generate_story(request: StoryGenerateRequest, gender: Optional[str] = None) -> Tuple[Optional[str], str, Optional[str]]:
        """
        Generates a personalised Confession, Meditation, or Transformation
        using SuperGrok. Prompt templates live in app/utils/prompts.py.
        For confessions, uses LLM_TEMPERATURE_CONFESSION to preserve the original
        story fidelity and prevent summarization or hallucination.
        """
        if request.story_type == StoryType.confession:
            llm = get_story_llm(
                temperature=settings.LLM_TEMPERATURE_CONFESSION,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
        elif request.story_type == StoryType.meditation:
            llm = get_story_llm(
                temperature=getattr(settings, "LLM_TEMPERATURE_MEDITATION", 0.35),
                max_tokens=settings.LLM_MAX_TOKENS,
            )
        else:
            llm = get_story_llm(max_tokens=settings.LLM_MAX_TOKENS)

        system_template = build_story_system_template(request.story_type, gender=gender)
        user_context = build_user_context(request)

        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template(STORY_HUMAN_TEMPLATE),
        ])

        formatted_messages = chat_prompt.format_prompt(
            user_context=user_context,
            story_type=request.story_type.value,
            **cover_identity_template_vars(
                request.first_name, request.gender, request.location
            ),
        ).to_messages()

        response = llm.invoke(formatted_messages)
        content = response.content.strip()

        # Clean up any potential markdown code block wrappers
        if content.startswith("```"):
            content = re.sub(r"^```(?:\w+)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content).strip()
        
        title = None
        image_prompt = None
        story_text = content
        
        if "TITLE:" in content and "STORY:" in content:
            if "IMAGE_PROMPT:" in content:
                parts_story = content.split("STORY:", 1)
                story_text = parts_story[1].strip()
                
                title_and_prompt = parts_story[0]
                parts_prompt = title_and_prompt.split("IMAGE_PROMPT:", 1)
                
                title = parts_prompt[0].replace("TITLE:", "").strip()
                image_prompt = parts_prompt[1].strip()
            else:
                parts = content.split("STORY:", 1)
                title = parts[0].replace("TITLE:", "").strip()
                story_text = parts[1].strip()

        if request.title and request.title.strip() and (not title or title == "Untitled"):
            title = request.title.strip()
            
        return title, story_text, image_prompt

    @staticmethod
    def generate_hero_hook(
        story_text: str,
        story_type: str = "confession",
        title: Optional[str] = None,
    ) -> Optional[str]:
        """
        Writes a 2–4 sentence public teaser from the finished story.
        Returns None when the model call fails so callers can fall back.
        """
        if not story_text or not story_text.strip():
            return None

        try:
            llm = get_story_llm()
            chat_prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(HERO_HOOK_SYSTEM),
                HumanMessagePromptTemplate.from_template(HERO_HOOK_HUMAN),
            ])
            messages = chat_prompt.format_prompt(
                story_type=story_type,
                title=(title or "").strip() or "Untitled",
                story_text=story_text.strip()[:8000],
            ).to_messages()
            response = llm.invoke(messages)
            hook = (response.content or "").strip()
            if hook.startswith("```"):
                hook = re.sub(r"^```(?:\w+)?\s*", "", hook)
                hook = re.sub(r"\s*```$", "", hook)
            hook = hook.strip().strip('"').strip("'").strip()
            return hook or None
        except Exception as exc:
            logger.warning("Hero hook generation failed: %s", exc, exc_info=True)
            return None

    @staticmethod
    def generate_hero_tagline(
        story_text: str,
        story_type: str = "confession",
        title: Optional[str] = None,
    ) -> Optional[str]:
        """
        Writes a two-line all-caps brush headline. Returns None on failure
        so the public page can fall back to the story title.
        """
        if not story_text or not story_text.strip():
            return None

        try:
            llm = get_story_llm()
            chat_prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(HERO_TAGLINE_SYSTEM),
                HumanMessagePromptTemplate.from_template(HERO_TAGLINE_HUMAN),
            ])
            messages = chat_prompt.format_prompt(
                story_type=story_type,
                title=(title or "").strip() or "Untitled",
                story_text=story_text.strip()[:8000],
            ).to_messages()
            response = llm.invoke(messages)
            line = (response.content or "").strip()
            if line.startswith("```"):
                line = re.sub(r"^```(?:\w+)?\s*", "", line)
                line = re.sub(r"\s*```$", "", line)
            line = line.strip().strip('"').strip("'").strip()
            line = re.sub(r"\n{3,}", "\n\n", line)
            return line or None
        except Exception as exc:
            logger.warning("Hero tagline generation failed: %s", exc, exc_info=True)
            return None

    @staticmethod
    def persist_hero_hook(story_row, story_text: str) -> None:
        """Sets story.hero_hook and story.hero_tagline from the LLM.

        Stores a full details-page teaser (2–4 sentences). Cover cards clamp
        description length separately in story_to_cover_template_payload —
        do not apply the 77-char cover limit here.
        """
        from app.utils.story_cover import (
            SUBTITLE_LINE_HARD_LIMIT,
            SUBTITLE_LINE_SOFT_LIMIT,
            format_two_line_field,
        )

        story_type = (
            story_row.story_type.value
            if getattr(story_row.story_type, "value", None)
            else str(story_row.story_type or "confession")
        )
        hook = AIService.generate_hero_hook(
            story_text,
            story_type=story_type,
            title=story_row.title,
        )
        raw_hook = hook or build_excerpt(story_text, max_chars=450)
        if raw_hook:
            # Light cleanup only — keep multi-sentence teasers intact.
            story_row.hero_hook = re.sub(r"\s+", " ", raw_hook).strip()
        else:
            story_row.hero_hook = None
        tagline = AIService.generate_hero_tagline(
            story_text,
            story_type=story_type,
            title=story_row.title,
        )
        story_row.hero_tagline = (
            format_two_line_field(
                tagline,
                SUBTITLE_LINE_HARD_LIMIT,
                wrap_soft_limit=SUBTITLE_LINE_SOFT_LIMIT,
            )
            if tagline
            else None
        )

    @staticmethod
    def _llm_text(response) -> str:
        content = getattr(response, "content", None)
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    text = getattr(block, "text", None)
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return str(content)

    @staticmethod
    def _parse_json_object(raw: str) -> Dict[str, Any]:
        text = (raw or "").strip().replace("\ufeff", "")
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        candidates = [text]
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
        last_err: Optional[Exception] = None
        for candidate in candidates:
            for payload in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError as exc:
                    last_err = exc
        raise last_err or ValueError("No JSON object in model output")

    @staticmethod
    def _moods_from_labeled(raw: str) -> Dict[str, Any]:
        tags: list[str] = []
        growth: list[str] = []
        life_phase = None
        for line in (raw or "").splitlines():
            stripped = line.strip().lstrip("-*• ")
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key = re.sub(r"[^a-z_]", "", key.strip().lower().replace(" ", "_"))
            value = value.strip().strip('"').strip("'")
            parts = [part.strip() for part in re.split(r"[,;|/]", value) if part.strip()]
            if key in {"tags", "tag", "themes", "moods"}:
                tags = parts
            elif key in {"growth_areas", "growth", "growth_area", "areas"}:
                growth = parts
            elif key in {"life_phase", "lifephase", "phase"}:
                life_phase = value or None
        return {
            "tags": tags,
            "growth_areas": growth,
            "life_phase": life_phase,
        }

    @staticmethod
    def _normalize_moods(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tags = parsed.get("tags") or parsed.get("themes") or parsed.get("moods") or []
        growth = parsed.get("growth_areas") or parsed.get("growth") or []
        if isinstance(tags, str):
            tags = [part.strip() for part in re.split(r"[,;]", tags) if part.strip()]
        if isinstance(growth, str):
            growth = [part.strip() for part in re.split(r"[,;]", growth) if part.strip()]
        if not isinstance(tags, list):
            tags = []
        if not isinstance(growth, list):
            growth = []
        life_phase = parsed.get("life_phase") or parsed.get("phase")
        if isinstance(life_phase, str):
            life_phase = life_phase.strip() or None
        else:
            life_phase = None
        result = {
            "tags": [str(t).strip() for t in tags if str(t).strip()][:8],
            "growth_areas": [str(g).strip() for g in growth if str(g).strip()][:4],
            "life_phase": life_phase,
        }
        if not result["tags"] and not result["growth_areas"] and not result["life_phase"]:
            return None
        return result

    @staticmethod
    def generate_moods(
        story_text: str,
        story_type: str = "confession",
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Suggest tags, growth_areas, and life_phase. Returns None on failure."""
        if not story_text or not story_text.strip():
            return None
        try:
            llm = get_story_llm()
            # Do not use ChatPromptTemplate here: the JSON example braces are
            # treated as template variables and the call fails before the LLM.
            system = EDITORIAL_MOODS_SYSTEM.replace("{{", "{").replace("}}", "}")
            human = (
                EDITORIAL_MOODS_HUMAN.replace("{story_type}", story_type)
                .replace("{title}", (title or "").strip() or "Untitled")
                .replace("{story_text}", story_text.strip()[:8000])
            )
            response = llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=human),
            ])
            raw = AIService._llm_text(response)
            parsed: Dict[str, Any] = {}
            try:
                parsed = AIService._parse_json_object(raw)
            except Exception:
                parsed = AIService._moods_from_labeled(raw)
            if isinstance(parsed, dict):
                parsed = {
                    str(key).strip().lower().replace(" ", "_"): value
                    for key, value in parsed.items()
                }
            moods = AIService._normalize_moods(parsed)
            if moods:
                return moods
            labeled = AIService._normalize_moods(AIService._moods_from_labeled(raw))
            if labeled:
                return labeled
            logger.warning("Mood suggestion empty. Raw: %s", (raw or "")[:400])
            return None
        except Exception as exc:
            logger.warning("Mood suggestion failed: %s", exc, exc_info=True)
            return None

    @staticmethod
    def generate_editorial_brief(
        story_text: str,
        story_type: str = "confession",
        title: Optional[str] = None,
        first_name: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> Optional[str]:
        """Private admin analysis paragraph. Returns None on failure."""
        if not story_text or not story_text.strip():
            return None
        try:
            llm = get_story_llm()
            chat_prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(EDITORIAL_BRIEF_SYSTEM),
                HumanMessagePromptTemplate.from_template(EDITORIAL_BRIEF_HUMAN),
            ])
            messages = chat_prompt.format_prompt(
                story_type=story_type,
                title=(title or "").strip() or "Untitled",
                first_name=(first_name or "").strip() or "—",
                tags=", ".join(tags) if tags else "None",
                story_text=story_text.strip()[:8000],
            ).to_messages()
            response = llm.invoke(messages)
            brief = (response.content or "").strip()
            if brief.startswith("```"):
                brief = re.sub(r"^```(?:\w+)?\s*", "", brief)
                brief = re.sub(r"\s*```$", "", brief)
            return brief.strip() or None
        except Exception as exc:
            logger.warning("Editorial brief generation failed: %s", exc, exc_info=True)
            return None

    @staticmethod
    def resolve_voice(
        gender: Optional[str] = None,
        text: Optional[str] = None,
        voice_name: Optional[str] = None,
        custom_voice_id: Optional[str] = None,
    ) -> Tuple[str, str, bool]:
        """
        Decides which voice narrates a story, in priority order:
          1. the member's own cloned voice, when one is supplied
          2. an explicitly chosen voice from the member-selectable catalog
          3. a gender- and language-consistent pick from the curated list

        Returns (voice_name, provider_voice_id, uses_custom_voice).
        """
        from app.core.llm import ELEVENLABS_VOICES, canonical_voice_name

        if custom_voice_id:
            return (voice_name or "My Voice"), custom_voice_id, True

        if voice_name:
            canonical = canonical_voice_name(voice_name)
            if canonical:
                return canonical, ELEVENLABS_VOICES[canonical], False

        auto = AIService.select_voice_by_gender(gender, text=text)
        return auto, ELEVENLABS_VOICES[auto], False

    @staticmethod
    def narrate_text(
        text: str,
        story_type,
        voice_id: str,
    ) -> Tuple[str, Optional[list]]:
        """
        Runs text through TTS and stores the result.
        Returns (audio_path, word_alignment).
        """
        audio_bytes, alignment = generate_voice_elevenlabs(
            text=text,
            voice_id=voice_id,
            return_timestamps=True,
            story_type=story_type,
        )
        return save_audio(audio_bytes), alignment

    @staticmethod
    def generate_and_voice_story(
        request: StoryGenerateRequest,
        gender: Optional[str] = None,
        voice_name: Optional[str] = None,
        custom_voice_id: Optional[str] = None,
    ) -> Tuple[Optional[str], str, str, str, Optional[str], Optional[list], str, bool]:
        """
        Generates a story with SuperGrok, then converts it to audio via
        ElevenLabs and saves it. When `voice_name` or `custom_voice_id` is given
        that voice is used; otherwise a gender-consistent premium voice is picked.

        Returns (title, story_text, audio_path, voice_name, image_prompt,
                 alignment, voice_id, uses_custom_voice).
        """
        title, story_text, image_prompt = AIService.generate_story(request, gender=gender)

        resolved_name, resolved_id, uses_custom = AIService.resolve_voice(
            gender=gender,
            text=story_text,
            voice_name=voice_name,
            custom_voice_id=custom_voice_id,
        )

        audio_path, alignment = AIService.narrate_text(
            text=story_text,
            story_type=request.story_type,
            voice_id=resolved_id,
        )
        return (
            title, story_text, audio_path, resolved_name,
            image_prompt, alignment, resolved_id, uses_custom,
        )

    # --- Background worker — story generation --------------------------------

    @staticmethod
    def _keep_submitted_narration(request, story_row) -> bool:
        """True when the member uploaded finished audio: keep their script, skip rewrite/TTS."""
        request_mode = getattr(request, "submission_mode", None)
        request_mode_value = getattr(request_mode, "value", request_mode)
        row_mode = getattr(story_row, "submission_mode", None) if story_row else None
        row_mode_value = getattr(row_mode, "value", row_mode)
        return bool(
            getattr(request, "skip_rewrite", False)
            or request_mode_value == "human_ready"
            or row_mode_value == "human_ready"
            or (story_row and story_row.audio_path)
        )

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
        from app.model.profile import UserProfile

        db = SessionLocal()
        try:
            story_row = db.query(StoryModel).filter(
                StoryModel.id == story_db_id
            ).first()
            if not story_row:
                logger.error(f"[Job {job_id}] Story row not found.")
                return

            gender = None
            custom_voice_id = None
            if story_row:
                # Per-story identity, not the member's saved profile. SubmitWizard
                # usually sends voice_name, so live TTS is unchanged. API/bulk jobs
                # that omit both voice_name and gender now get unspecified PERSPECTIVE
                # (not a silent female default); auto voice pick stays a mixed pool.
                gender = story_row.gender or getattr(request, "gender", None)
            if story_row and story_row.user_id:
                profile_row = db.query(UserProfile).filter(UserProfile.user_id == story_row.user_id).first()
                if profile_row and getattr(request, "use_custom_voice", False):
                    custom_voice_id = profile_row.custom_voice_id

            keep_submitted = AIService._keep_submitted_narration(request, story_row)

            if keep_submitted:
                title = None
                story_text = (
                    (story_row.story_input or getattr(request, "story_input", None) or "")
                ).strip()
                if not story_text:
                    raise ValueError("Fully narrated submissions need the finished text.")
                image_prompt = None
                audio_path = story_row.audio_path
                voice_name = "Member narration"
                alignment = None
                voice_id = None
                uses_custom_voice = False
            else:
                (
                    title, story_text, audio_path, voice_name,
                    image_prompt, alignment, voice_id, uses_custom_voice,
                ) = AIService.generate_and_voice_story(
                    request,
                    gender=gender,
                    voice_name=getattr(request, "voice_name", None),
                    custom_voice_id=custom_voice_id,
                )

            # Simple duration estimation (150 wpm) and default voice lookup
            story_row.voice_name = voice_name
            story_row.voice_id = voice_id
            story_row.uses_custom_voice = uses_custom_voice
            word_count = len(story_text.split()) if story_text else 0
            duration_secs = int((word_count / 150) * 60)

            # Strip break tags before saving to DB
            story_text_db = re.sub(r'<break\s+time="[^"]+"\s*/>', '', story_text)

            story_data.complete_story(
                db=db,
                story=story_row,
                story_text=story_text_db,
                title=title,
                audio_path=audio_path,
                audio_duration_seconds=duration_secs,
                alignment=alignment,
            )

            AIService.persist_hero_hook(story_row, story_text_db)

            from app.utils.story_cover import try_generate_story_cover

            logger.info(f"Triggering cover generation for story {story_row.id}...")
            try_generate_story_cover(db, story_row, image_prompt=image_prompt)

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
                    # The credit was spent when the job was queued; give it back
                    # so a provider outage doesn't cost the member a generation.
                    if story_row.user_id:
                        from app.data.credit import refund_credit
                        refund_credit(db, str(story_row.user_id))
            except Exception:
                logger.warning(f"[Job {job_id}] Could not record failure state.", exc_info=True)
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
                title=f"Story about {topic}",
                first_name="Anonymous",
                story_input=topic,
            )

            # 2. Call AIService.generate_and_voice_story(request)
            # Intentional: bulk jobs omit gender, so PERSPECTIVE is unspecified
            # (no longer a silent female default). TTS auto-pick is unchanged.
            (
                title, story_text, audio_path, voice_name,
                image_prompt, alignment, voice_id, uses_custom_voice,
            ) = AIService.generate_and_voice_story(request)

            # Save the chosen voice name to the database row
            story_row.voice_name = voice_name
            story_row.voice_id = voice_id
            story_row.uses_custom_voice = uses_custom_voice

            # Strip break tags before saving to DB
            story_text_db = re.sub(r'<break\s+time="[^"]+"\s*/>', '', story_text)

            # 3. Call story_data.complete_story() to save text + audio_path
            story_data.complete_story(
                db=db,
                story=story_row,
                story_text=story_text_db,
                title=title,
                audio_path=audio_path,
                alignment=alignment,
            )

            AIService.persist_hero_hook(story_row, story_text_db)
            
            # Try generating a story-specific AI cover unless the member uploaded one.
            from app.model.story import ImageSource
            from app.utils.story_cover import try_generate_story_cover

            if story_row.image_source != ImageSource.user_uploaded:
                try_generate_story_cover(db, story_row, image_prompt=image_prompt)

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
                    # Lets the route confirm the caller owns this job before
                    # returning the full story text.
                    "owner_user_id": str(story.user_id) if story.user_id else None,
                }
            
            # 2. Check Liberation Definitions
            definition = db.query(LiberationDefinition).filter(LiberationDefinition.job_id == job_id).first()
            if definition:
                return {
                    "status": definition.generation_status,
                    "title": definition.title,
                    "audio_path": None,
                    "story_text": f"Liberation Journey Blueprint with {definition.total_days} days.",
                    "owner_user_id": None,
                }
                
            return None
        finally:
            db.close()
