import os
import uuid
import requests
from pathlib import Path
from langchain_openai import ChatOpenAI
from app.core.config import settings


# ElevenLabs TTS & LLM Configuration for House of Juliette
# ---------------------------------------------------------------------------
# LLM — SuperGrok (xAI)
# ---------------------------------------------------------------------------

def get_story_llm(
    temperature: float | None = None,
    model_name: str | None = None,
):
    """
    Returns a SuperGrok LangChain-compatible LLM instance.
    Model name and temperature are loaded from settings (config.py / .env).

    Override via .env:
        LLM_MODEL=grok-3-mini          # cheaper/faster
        LLM_TEMPERATURE_STORY=0.9      # more creative
    """
    if not settings.XAI_API_KEY:
        raise ValueError("XAI_API_KEY is missing. Add it to your .env file.")

    return ChatOpenAI(
        api_key=settings.XAI_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=model_name or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE_STORY,
    )


# Curated list of high-quality premium pre-made ElevenLabs voices
ELEVENLABS_VOICES = {
    "Rachel": "21m00Tcm4TlvDq8ikWAM",      # Warm & Friendly (Female)
    "Antoni": "ErXwobaYiN019PkySvjV",      # Calm & Reassuring (Male)
    "Bella": "EXAVITQu4vr4xnSDxMaL",       # Soft & Meditative (Female)
    "Adam": "pNInz6obpgDQGcFmaJgB",        # Dominant, Firm (Male)
    "Glinda": "z9fAnwCtxredmBiSV157",      # Warm & Emotional (Female)
    "Liam": "TX3da5IXgTnvGWJ25ANZ",        # Bright & Conversational (Male)
    "Charlotte": "XB0yd4OOqHR45ZJA2t78",   # Sincere & Gentle (Female)
    "George": "JBFvJZJe25aE5gtRx489",      # Soothing British (Male)
    "Sophia": "u8ADrbquiJqufR9XMtb8",      # Client Preferred Meditative Voice (Female)
}

def generate_voice_elevenlabs(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
    stability: float | None = None,
    similarity_boost: float | None = None,
    style: float | None = None,
) -> bytes:
    """
    Generates audio from text using ElevenLabs API.
    Returns the generated audio as raw MP3 bytes.

    All voice parameters are loaded from settings (config.py / .env) by default.
    If parameters are not provided, they are randomized slightly to provide unique variations.

    Requires ELEVENLABS_API_KEY in .env.
    """
    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY == "your_elevenlabs_api_key_here":
        # MOCK TTS: Return a tiny empty mp3 byte string so the job completes successfully during testing
        return b"ID3\x04\x00\x00\x00\x00\x00\x00"

    # Resolve voice ID from name (e.g. "Rachel" -> "21m00Tcm4TlvDq8ikWAM")
    resolved_voice_id = ELEVENLABS_VOICES.get(voice_id, voice_id) or settings.ELEVENLABS_VOICE_ID
    resolved_model_id = model_id or settings.ELEVENLABS_MODEL_ID

    # Generate or resolve random variations for voice settings if not explicitly specified
    # stability (0.50-0.60): slightly higher stability prevents the voice (especially Sophia in Dutch) 
    # from stumbling or being inconsistent, while keeping it expressive, warm, and emotional.
    # similarity_boost (0.80-0.90): retains high clarity of the selected voice.
    # style (0.35-0.55): higher style amplifies the unique character and emotional depth of the narration.
    import random
    resolved_stability = stability
    if resolved_stability is None:
        # If the voice is Sophia, use a slightly higher stability to prevent multilingual stumbling
        if voice_id == "Sophia" or resolved_voice_id == ELEVENLABS_VOICES.get("Sophia"):
            resolved_stability = round(random.uniform(0.55, 0.65), 2)
        else:
            resolved_stability = round(random.uniform(0.50, 0.60), 2)

    resolved_similarity_boost = similarity_boost
    if resolved_similarity_boost is None:
        resolved_similarity_boost = round(random.uniform(0.80, 0.90), 2)

    resolved_style = style
    if resolved_style is None:
        resolved_style = round(random.uniform(0.35, 0.55), 2)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": settings.ELEVENLABS_API_KEY,
    }

    data = {
        "text": text,
        "model_id": resolved_model_id,
        "voice_settings": {
            "stability": resolved_stability,
            "similarity_boost": resolved_similarity_boost,
            "style": resolved_style,
            "use_speaker_boost": True,
        },
    }

    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()

    return response.content


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
