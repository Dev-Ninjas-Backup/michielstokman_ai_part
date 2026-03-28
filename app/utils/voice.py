import os
import requests
from typing import Optional

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
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        api_key = "your-elevenlabs-api-key" # Fallback/placeholder

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
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
