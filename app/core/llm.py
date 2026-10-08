import os
import uuid
import requests
from pathlib import Path
import threading
from langchain_openai import ChatOpenAI
from app.core.config import settings

_tts_v2_fallback_count = 0
_tts_v2_fallback_lock = threading.Lock()


def get_tts_v2_fallback_count() -> int:
    """Returns the total number of times the V2 TTS pipeline has fallen back to legacy."""
    with _tts_v2_fallback_lock:
        return _tts_v2_fallback_count


# ElevenLabs TTS & LLM Configuration for House of Juliette
# ---------------------------------------------------------------------------
# LLM — SuperGrok (xAI)
# ---------------------------------------------------------------------------

def get_story_llm(
    temperature: float | None = None,
    model_name: str | None = None,
    max_tokens: int | None = None,
):
    """
    Returns a SuperGrok LangChain-compatible LLM instance.
    Model name and temperature are loaded from settings (config.py / .env).

    Override via .env:
        LLM_MODEL=grok-3-mini          # cheaper/faster
        LLM_TEMPERATURE_STORY=0.9      # more creative
        LLM_TEMPERATURE_CONFESSION=0.35 # fidelity for confessions
        LLM_MAX_TOKENS=8192            # output token budget
    """
    if not settings.XAI_API_KEY:
        raise ValueError("XAI_API_KEY is missing. Add it to your .env file.")

    kwargs = {
        "api_key": settings.XAI_API_KEY,
        "base_url": settings.LLM_BASE_URL,
        "model": model_name or settings.LLM_MODEL,
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE_STORY,
    }
    resolved_max_tokens = max_tokens if max_tokens is not None else getattr(settings, "LLM_MAX_TOKENS", None)
    if resolved_max_tokens is not None:
        kwargs["max_tokens"] = resolved_max_tokens

    return ChatOpenAI(**kwargs)


# Curated list of high-quality premium pre-made ElevenLabs voices
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

ELEVENLABS_VOICES = {
    "Charlotte": "aRlmTYIQo6Tlg5SlulGC",   # Client Preferred soft/gentle (Female)
    "Sophia": "u8ADrbquiJqufR9XMtb8",      # Client Preferred Meditative Voice (Female)
    "Calen": "S44KQ3oLFckbxgyKfold",       # Resonant, Magnetic (Male)
    "Victoria": "WeAAwKYcS06VmXw086yZ",    # Warm and Calm French (Female)
    "Anja": "ytIo1w3M21piPjpR44FO",        # Cloned Female (Anja / Louise Porter)
    "Chapter1": "DGU073R3uvEaw6TvrL1r",    # Cloned Female (Chapter 1)
}

# The subset of voices members may choose from, in display order. Anja and
# Chapter1 stay out of the catalog — they are reserved for admin/editorial use.
MEMBER_VOICE_CATALOG = [
    {
        "name": "Sophia",
        "label": "Sophia",
        "gender": "female",
        "language": "english",
        "description": "Soft, meditative and unhurried. The default for guided meditations.",
    },
    {
        "name": "Charlotte",
        "label": "Charlotte",
        "gender": "female",
        "language": "english",
        "description": "Gentle and close, like a friend speaking just above a whisper.",
    },
    {
        "name": "Calen",
        "label": "Calen",
        "gender": "male",
        "language": "english",
        "description": "Resonant and magnetic, with a grounded low register.",
    },
    {
        "name": "Victoria",
        "label": "Victoria",
        "gender": "female",
        "language": "french",
        "description": "Warm and calm, tuned for French-language narration.",
    },
    {
        "name": "Anja",
        "label": "Anja",
        "gender": "female",
        "language": "english",
        "description": "Rich and expressive, with a storyteller's cadence.",
    },
]

MEMBER_VOICE_NAMES = [voice["name"] for voice in MEMBER_VOICE_CATALOG]

# Short lines the member hears in the voice picker. Kept here so the sample
# matches the language of the voice rather than always being English.
VOICE_PREVIEW_LINES = {
    "english": "Welcome. This is how I will tell your story — slowly, clearly, and close.",
    "french": "Bienvenue. Voici comment je raconterai votre histoire — posément, clairement, tout près.",
}

_EL_PREVIEW_BY_ID: dict[str, str] | None = None
_PREVIEW_LOCK = None  # set lazily so importing this module stays cheap


def voice_preview_text(language: str | None = None) -> str:
    key = (language or "english").strip().lower()
    return VOICE_PREVIEW_LINES.get(key, VOICE_PREVIEW_LINES["english"])


def _preview_lock():
    global _PREVIEW_LOCK
    if _PREVIEW_LOCK is None:
        import threading

        _PREVIEW_LOCK = threading.Lock()
    return _PREVIEW_LOCK


def _elevenlabs_preview_map() -> dict[str, str]:
    """
    One ElevenLabs /voices call, then reuse it for the life of the process.
    Each premade voice already has a public preview clip on their CDN.
    """
    global _EL_PREVIEW_BY_ID
    if _EL_PREVIEW_BY_ID is not None:
        return _EL_PREVIEW_BY_ID

    _EL_PREVIEW_BY_ID = {}
    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        return _EL_PREVIEW_BY_ID

    try:
        response = requests.get(
            f"{ELEVENLABS_API_BASE}/voices",
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
            timeout=12,
        )
        response.raise_for_status()
        for voice in response.json().get("voices") or []:
            voice_id = voice.get("voice_id")
            preview = voice.get("preview_url")
            if voice_id and preview:
                _EL_PREVIEW_BY_ID[voice_id] = preview
    except Exception:
        # Catalog still returns without previews rather than failing the picker.
        pass
    return _EL_PREVIEW_BY_ID


def get_voice_preview_url(
    voice_name: str,
    voice_id: str | None = None,
    language: str | None = None,
) -> str | None:
    """
    A playable MP3 URL for the voice picker.

    Prefers a locally cached clip so the sample sounds like our narration.
    Falls back to ElevenLabs' own preview, then generates and caches a short
    clip with the same TTS path stories use.
    """
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in (voice_name or "voice")).strip("-") or "voice"
    cache_rel = f"media/audio/voice-previews/{slug}.mp3"
    cache_path = Path(cache_rel)

    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_rel

    resolved_id = ELEVENLABS_VOICES.get(voice_name, voice_id) or voice_id
    el_preview = _elevenlabs_preview_map().get(resolved_id or "")
    if el_preview:
        return el_preview

    with _preview_lock():
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_rel
        try:
            audio = generate_voice_elevenlabs(
                voice_preview_text(language),
                voice_id=resolved_id or voice_name,
                story_type="confession",
            )
            if isinstance(audio, tuple):
                audio = audio[0]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(audio)
            return cache_rel
        except Exception:
            return None


def is_selectable_voice(voice_name: str | None) -> bool:
    """True when `voice_name` is one of the voices members are allowed to pick."""
    if not voice_name:
        return False
    return any(voice_name.lower() == name.lower() for name in MEMBER_VOICE_NAMES)


def canonical_voice_name(voice_name: str) -> str | None:
    """Resolves a case-insensitive voice name to its catalog spelling."""
    for name in MEMBER_VOICE_NAMES:
        if voice_name.lower() == name.lower():
            return name
    return None

# Curated, optimized settings for pre-made voices to prevent stumbling
# and optimize quality specifically for confessions vs meditations.
VOICE_OPTIMIZATION = {
    "Sophia": {
        "confession": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.65, "speed": 0.88},
        "meditation": {"stability": 0.62, "similarity_boost": 0.85, "style": 0.50, "speed": 0.88},
        "transformation": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.60, "speed": 0.90},
    },
    "Chapter1": {
        "confession": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.60, "speed": 0.88},
        "meditation": {"stability": 0.65, "similarity_boost": 0.85, "style": 0.50, "speed": 0.88},
        "transformation": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.60, "speed": 0.90},
    },
    "Calen": {
        "confession": {"stability": 0.52, "similarity_boost": 0.85, "style": 0.40, "speed": 1.15},
        "meditation": {"stability": 0.60, "similarity_boost": 0.85, "style": 0.35, "speed": 1.08},
        "transformation": {"stability": 0.52, "similarity_boost": 0.85, "style": 0.40, "speed": 1.15},
    },
    "Charlotte": {
        "confession": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.65, "speed": 0.88},
        "meditation": {"stability": 0.65, "similarity_boost": 0.85, "style": 0.50, "speed": 0.88},
        "transformation": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.60, "speed": 0.90},
    },
    "Victoria": {
        "confession": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.18, "speed": 1.00},
        "meditation": {"stability": 0.60, "similarity_boost": 0.85, "style": 0.15, "speed": 0.90},
        "transformation": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.18, "speed": 1.00},
    },
    "Anja": {
        "confession": {"stability": 0.52, "similarity_boost": 0.86, "style": 0.42, "speed": 1.02},
        "meditation": {"stability": 0.58, "similarity_boost": 0.86, "style": 0.35, "speed": 0.92},
        "transformation": {"stability": 0.52, "similarity_boost": 0.86, "style": 0.42, "speed": 1.02},
    }
}

def parse_alignment_to_words(alignment: dict) -> list[dict]:
    """
    Parses character-level alignments from ElevenLabs response into word-level alignments.
    Returns list of dicts: [{'word': str, 'start': float, 'end': float}]
    """
    if not alignment:
        return []
    characters = alignment.get("characters", [])
    start_times = alignment.get("character_start_times_seconds", [])
    end_times = alignment.get("character_end_times_seconds", [])
    
    if not characters or not start_times or not end_times:
        return []
        
    words = []
    current_word = []
    word_start = None
    
    # Standard separators (excluding apostrophe to keep words like don't, let's intact)
    separators = {
        ' ', '\t', '\n', '\r', '.', ',', '!', '?', ';', ':', '-', '—', 
        '"', '“', '”', '‘', '’', '(', ')', '[', ']', '{', '}', '*', 
        '<', '>', '/', '\\', '_', '@', '#', '$', '%', '^', '&', '+'
    }
    
    for idx, char in enumerate(characters):
        if idx >= len(start_times) or idx >= len(end_times):
            break
            
        start = start_times[idx]
        end = end_times[idx]
        
        if char in separators:
            if current_word:
                words.append({
                    "word": "".join(current_word),
                    "start": word_start,
                    "end": end_times[idx - 1]
                })
                current_word = []
                word_start = None
        else:
            if not current_word:
                word_start = start
            current_word.append(char)
            
    if current_word:
        words.append({
            "word": "".join(current_word),
            "start": word_start,
            "end": end_times[min(len(end_times) - 1, len(characters) - 1)]
        })
        
    return words


def _generate_voice_elevenlabs_v2(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
    stability: float | None = None,
    similarity_boost: float | None = None,
    style: float | None = None,
    speed: float | None = None,
    return_timestamps: bool = True,
    story_type: str | None = None,
) -> bytes | tuple[bytes, list[dict]]:
    """
    Phase 2 TTS V2 pipeline: chunking, concurrency, alignment-based trimming,
    and single-pass loudness normalization. Resolves curated voice calibrations
    (e.g. Calen pacing, Victoria/Anja stability & emotion) from VOICE_OPTIMIZATION.
    """
    from app.services.tts_pipeline import execute_tts_pipeline_v2

    friendly_name = None
    if voice_id:
        v_str = str(voice_id).strip().lower()
        for name, vid in ELEVENLABS_VOICES.items():
            if vid.lower() == v_str or name.lower() == v_str:
                friendly_name = name
                break

    is_meditation = False
    is_transformation = False
    if story_type:
        st_val = str(story_type.value if hasattr(story_type, "value") else story_type).lower()
        if "meditation" in st_val:
            is_meditation = True
        elif "transformation" in st_val:
            is_transformation = True
    else:
        if '<break time="3.0s"' in text or '<break time="3s"' in text:
            is_meditation = True

    opt_key = "meditation" if is_meditation else ("transformation" if is_transformation else "confession")

    resolved_stability = stability
    resolved_similarity_boost = similarity_boost
    resolved_style = style
    resolved_speed = speed

    if friendly_name and friendly_name in VOICE_OPTIMIZATION:
        voice_opts = VOICE_OPTIMIZATION[friendly_name]
        chosen_opt = voice_opts.get(opt_key) or voice_opts.get("confession", {})
        if resolved_stability is None:
            resolved_stability = chosen_opt.get("stability")
        if resolved_similarity_boost is None:
            resolved_similarity_boost = chosen_opt.get("similarity_boost")
        if resolved_style is None:
            resolved_style = chosen_opt.get("style")
        if resolved_speed is None:
            resolved_speed = chosen_opt.get("speed")

    audio_bytes, alignment = execute_tts_pipeline_v2(
        text=text,
        story_type=story_type,
        voice_id=voice_id,
        model_id=model_id,
        stability=resolved_stability,
        similarity_boost=resolved_similarity_boost,
        style=resolved_style,
        speed=resolved_speed,
        return_timestamps=return_timestamps,
    )
    if return_timestamps:
        return audio_bytes, alignment
    return audio_bytes


def generate_voice_elevenlabs(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
    stability: float | None = None,
    similarity_boost: float | None = None,
    style: float | None = None,
    speed: float | None = None,
    return_timestamps: bool = False,
    story_type: str | None = None,
) -> bytes | tuple[bytes, list[dict]]:
    """
    Generates audio from text using ElevenLabs API.
    Returns the generated audio as raw MP3 bytes (or a tuple of bytes and word alignment JSON if return_timestamps is True).

    All voice parameters are loaded from settings (config.py / .env) by default.
    If parameters are not provided, they are resolved to curated, optimized settings.

    Requires ELEVENLABS_API_KEY in .env.
    """
    # Safety mechanism: Run V2 pipeline only when TTS_PIPELINE_V2 is enabled for story narrations.
    # On any exception, log error without story text and fall back cleanly to legacy path.
    if getattr(settings, "TTS_PIPELINE_V2", False) and return_timestamps:
        try:
            return _generate_voice_elevenlabs_v2(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                speed=speed,
                return_timestamps=return_timestamps,
                story_type=story_type,
            )
        except Exception as exc:
            global _tts_v2_fallback_count
            with _tts_v2_fallback_lock:
                _tts_v2_fallback_count += 1
                cnt = _tts_v2_fallback_count
            import logging
            logging.getLogger(__name__).warning(
                "TTS V2 fallback [count=%d, error_type=%s]: Falling back to legacy TTS pipeline.",
                cnt,
                type(exc).__name__,
            )

    # Preprocess text to add breaks/pauses for a sensual, slow delivery
    import re
    # Strip markdown bold/italic tags so the TTS engine doesn't read them or glitch
    clean_text = text.replace("**", "").replace("*", "")
    
    # Parse explicit pause markers [6s], [pause 12s], [6s pause], etc. into chained breaks (max 3.0s limit, capped at 10s max)
    def parse_pauses(match):
        seconds = int(match.group(1))
        seconds = min(seconds, 10)  # Shorten pauses: cap at 10s max
        tags = []
        while seconds > 0:
            chunk = min(seconds, 3)
            tags.append(f'<break time="{chunk:.1f}s" />')
            seconds -= chunk
        return "".join(tags)
    clean_text = re.sub(r'\[(?:pause\s+)?(\d+)(?:\s*s|\s*sec|\s*seconds)?(?:\s+pause)?\]', parse_pauses, clean_text, flags=re.IGNORECASE)
    
    # Strip newlines and spaces immediately surrounding break tags to prevent duplicate padding
    clean_text = re.sub(r'\s*\n\s*((?:<break time="[^"]+" />\s*)+)\s*\n\s*', r' \1 ', clean_text)
    clean_text = re.sub(r'\s*((?:<break time="[^"]+" />\s*)+)\s*\n\s*', r' \1 ', clean_text)
    clean_text = re.sub(r'\s*\n\s*((?:<break time="[^"]+" />\s*)+)\s*', r' \1 ', clean_text)
    
    # 1. Paragraph breaks (double newlines) -> 2.0s pause
    processed_text = re.sub(r'\n\s*\n', '\n\n<break time="2.0s" />\n\n', clean_text)
    # 2. Line breaks (single newline) -> 1.2s pause
    processed_text = re.sub(r'(?<!\n)\n(?!\n)', '\n<break time="1.2s" />\n', processed_text)
    # 3. Ellipses (...) -> 0.5s pause
    processed_text = re.sub(r'\.\.\.+', '... <break time="0.5s" />', processed_text)
    # 4. Sentence endings (period, question mark, exclamation mark followed by space and Capital Letter) -> 1.0s pause
    processed_text = re.sub(r'([.!?])\s+([A-Z])', r'\1 <break time="1.0s" /> \2', processed_text)

    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        # MOCK TTS: Return a tiny empty mp3 byte string so the job completes successfully during testing
        mock_audio = b"ID3\x04\x00\x00\x00\x00\x00\x00"
        if return_timestamps:
            words_list = processed_text.split()
            mock_alignment = []
            for i, w in enumerate(words_list):
                if "<break" in w or "time=" in w:
                    continue
                mock_alignment.append({
                    "word": w.strip(".,!?\"()"),
                    "start": round(i * 0.4, 2),
                    "end": round(i * 0.4 + 0.3, 2)
                })
            return mock_audio, mock_alignment
        return mock_audio

    # Resolve voice ID from name (e.g. "Sophia" -> "u8ADrbquiJqufR9XMtb8")
    resolved_voice_id = ELEVENLABS_VOICES.get(voice_id, voice_id) or settings.ELEVENLABS_VOICE_ID
    resolved_model_id = model_id or settings.ELEVENLABS_MODEL_ID

    # Normalize story type to determine story delivery style
    is_meditation = False
    is_transformation = False
    if story_type:
        st_str = str(story_type).lower()
        if "meditation" in st_str:
            is_meditation = True
        elif "transformation" in st_str:
            is_transformation = True
    else:
        # Fallback: Infer meditation based on double newline break duration (3.0s is meditation)
        if '<break time="3.0s"' in text or '<break time="3s"' in text:
            is_meditation = True

    # Resolve friendly voice name for optimizations lookup
    friendly_name = None
    if voice_id:
        for name, vid in ELEVENLABS_VOICES.items():
            if vid == voice_id or name.lower() == voice_id.lower():
                friendly_name = name
                break

    opt_key = "meditation" if is_meditation else ("transformation" if is_transformation else "confession")

    # Resolve optimized voice settings
    resolved_stability = stability
    if resolved_stability is None:
        if friendly_name and friendly_name in VOICE_OPTIMIZATION:
            resolved_stability = VOICE_OPTIMIZATION[friendly_name][opt_key]["stability"]
        else:
            resolved_stability = 0.65 if is_meditation else 0.55

    resolved_similarity_boost = similarity_boost
    if resolved_similarity_boost is None:
        if friendly_name and friendly_name in VOICE_OPTIMIZATION:
            resolved_similarity_boost = VOICE_OPTIMIZATION[friendly_name][opt_key]["similarity_boost"]
        else:
            resolved_similarity_boost = 0.85

    resolved_style = style
    if resolved_style is None:
        if friendly_name and friendly_name in VOICE_OPTIMIZATION:
            resolved_style = VOICE_OPTIMIZATION[friendly_name][opt_key]["style"]
        else:
            resolved_style = 0.45 if is_meditation else 0.55

    resolved_speed = 0.80 if is_meditation else 0.88
    if friendly_name and friendly_name in VOICE_OPTIMIZATION:
        resolved_speed = VOICE_OPTIMIZATION[friendly_name][opt_key]["speed"]

    if return_timestamps:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}/with-timestamps"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "xi-api-key": settings.ELEVENLABS_API_KEY,
        }
    else:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": settings.ELEVENLABS_API_KEY,
        }

    data = {
        "text": processed_text,
        "model_id": resolved_model_id,
        "voice_settings": {
            "stability": resolved_stability,
            "similarity_boost": resolved_similarity_boost,
            "style": resolved_style,
            "use_speaker_boost": True,
            "speed": resolved_speed,
        },
    }

    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()

    if return_timestamps:
        import base64
        res_json = response.json()
        audio_bytes = base64.b64decode(res_json["audio_base64"])
        alignment = res_json.get("alignment", {})
        word_alignments = parse_alignment_to_words(alignment)
        return audio_bytes, word_alignments
    else:
        return response.content


# ---------------------------------------------------------------------------
# Voice cloning — ElevenLabs Instant Voice Cloning (IVC)
# ---------------------------------------------------------------------------

# ElevenLabs rejects very short samples outright and quality degrades badly
# below roughly a minute of speech, so reject obviously unusable uploads early.
MIN_VOICE_SAMPLE_BYTES = 32 * 1024
MAX_VOICE_SAMPLE_BYTES = 10 * 1024 * 1024


class VoiceCloningError(Exception):
    """Raised when ElevenLabs refuses or fails a voice-cloning request."""


def clone_voice_elevenlabs(
    display_name: str,
    samples: list[tuple[str, bytes, str]],
    description: str | None = None,
) -> str:
    """
    Creates an Instant Voice Clone from one or more recordings and returns the
    new provider voice_id.

    `samples` is a list of (filename, raw_bytes, content_type) tuples.

    Instant voice cloning requires a paid ElevenLabs plan; on free keys the API
    responds 401/403 and we surface that as a VoiceCloningError so the caller
    can degrade to the predefined voices instead of failing the whole request.
    """
    if not samples:
        raise VoiceCloningError("At least one voice recording is required.")

    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        # Mirror the mock TTS path so the feature is exercisable without a key.
        return f"mock-voice-{uuid.uuid4().hex[:12]}"

    files = [("files", (name, data, content_type)) for name, data, content_type in samples]
    payload = {"name": display_name}
    if description:
        payload["description"] = description

    try:
        response = requests.post(
            f"{ELEVENLABS_API_BASE}/voices/add",
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
            data=payload,
            files=files,
            timeout=180,
        )
    except requests.RequestException as exc:
        raise VoiceCloningError(f"Could not reach the voice provider: {exc}") from exc

    if response.status_code >= 400:
        detail = _extract_elevenlabs_error(response)
        if response.status_code in (401, 403):
            raise VoiceCloningError(
                "Voice cloning is not enabled on the configured ElevenLabs plan. "
                f"Provider said: {detail}"
            )
        raise VoiceCloningError(detail)

    voice_id = response.json().get("voice_id")
    if not voice_id:
        raise VoiceCloningError("Voice provider did not return a voice id.")
    return voice_id


def delete_cloned_voice(voice_id: str) -> bool:
    """Best-effort removal of a cloned voice from the provider account."""
    if not voice_id or voice_id.startswith("mock-voice-"):
        return True
    if not settings.ELEVENLABS_API_KEY:
        return False
    try:
        response = requests.delete(
            f"{ELEVENLABS_API_BASE}/voices/{voice_id}",
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
            timeout=30,
        )
        return response.status_code < 400
    except requests.RequestException:
        return False


def _extract_elevenlabs_error(response: "requests.Response") -> str:
    """Pulls a readable message out of an ElevenLabs error body."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or f"HTTP {response.status_code}"

    detail = body.get("detail", body)
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("status") or detail)[:300]
    return str(detail)[:300]


# ---------------------------------------------------------------------------
# Audio Storage — S3 / Local Fallback
# ---------------------------------------------------------------------------

AUDIO_STORAGE_DIR = Path("media/audio")


def save_audio(audio_bytes: bytes, filename: str | None = None) -> str:
    """
    Attempts to save raw audio bytes to AWS S3. 
    If S3 is not configured or fails, it falls back to local media/audio/ directory.
    Returns the URL or relative path, e.g. "https://mybucket.s3..." or "media/audio/abc123.mp3".
    """
    from app.utils.s3 import upload_audio_bytes_to_s3
    
    s3_url = upload_audio_bytes_to_s3(audio_bytes)
    if s3_url:
        return s3_url

    # Fallback to local storage
    AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f"{uuid.uuid4()}.mp3"

    file_path = AUDIO_STORAGE_DIR / filename
    file_path.write_bytes(audio_bytes)

    return str(file_path)
