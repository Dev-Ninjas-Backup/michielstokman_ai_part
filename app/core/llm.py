import requests
from langchain_openai import ChatOpenAI
from app.core.config import settings

def get_story_llm(temperature: float = 0.8, model_name: str = "grok-3"):
    """
    Returns an instance of SuperGrok (grok-3) for story generation.
    Uses the xAI API (https://api.x.ai/v1) — requires XAI_API_KEY in environment.
    Available models: grok-3, grok-3-fast, grok-3-mini, grok-3-mini-fast
    """
    if not settings.XAI_API_KEY:
        raise ValueError("XAI_API_KEY is missing in configuration")

    return ChatOpenAI(
        api_key=settings.XAI_API_KEY,
        base_url="https://api.x.ai/v1",
        model=model_name,
        temperature=temperature
    )

def generate_voice_elevenlabs(
    text: str,
    voice_id: str = "EXAVITQu4vr4xnSDxMaL",  # Default Bella voice or similar
    model_id: str = "eleven_monolingual_v1"
) -> bytes:
    """
    Generates audio from text using ElevenLabs API.
    Returns the generated audio as bytes.
    Requires ELEVENLABS_API_KEY environment variable.
    """
    if not settings.ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is missing in configuration")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": settings.ELEVENLABS_API_KEY
    }
    
    data = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    
    return response.content
