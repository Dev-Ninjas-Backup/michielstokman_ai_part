import os
import uuid
import requests
from pathlib import Path
from langchain_openai import ChatOpenAI
from app.core.config import settings


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
        base_url="https://api.x.ai/v1",
        model=model_name or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE_STORY,
    )


# ---------------------------------------------------------------------------
# TTS — ElevenLabs
# ---------------------------------------------------------------------------

def generate_voice_elevenlabs(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
) -> bytes:
    """
    Generates audio from text using ElevenLabs API.
    Returns the generated audio as raw MP3 bytes.

    All voice parameters are loaded from settings (config.py / .env):
        ELEVENLABS_VOICE_ID        → which voice to use
        ELEVENLABS_MODEL_ID        → TTS model quality
        ELEVENLABS_STABILITY       → warmth/consistency (0.0-1.0)
        ELEVENLABS_SIMILARITY_BOOST → expressiveness (0.0-1.0)
        ELEVENLABS_STYLE           → stylistic variation (0.0-1.0)

    Requires ELEVENLABS_API_KEY in .env.
    """
    if not settings.ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is missing. Add it to your .env file.")

    resolved_voice_id = voice_id or settings.ELEVENLABS_VOICE_ID
    resolved_model_id = model_id or settings.ELEVENLABS_MODEL_ID

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
            "stability": settings.ELEVENLABS_STABILITY,
            "similarity_boost": settings.ELEVENLABS_SIMILARITY_BOOST,
            "style": settings.ELEVENLABS_STYLE,
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
