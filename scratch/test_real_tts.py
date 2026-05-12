import os
from dotenv import load_dotenv
import requests

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") # Rachel
MODEL_ID = "eleven_turbo_v2_5"

print("Generating real audio via ElevenLabs...")

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
headers = {
    "Accept": "audio/mpeg",
    "Content-Type": "application/json",
    "xi-api-key": ELEVENLABS_API_KEY,
}
data = {
    "text": "Hello! Your ElevenLabs API key is now active and working perfectly. This is a real audio generation test.",
    "model_id": MODEL_ID,
    "voice_settings": {
        "stability": 0.5,
        "similarity_boost": 0.8
    }
}

try:
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        with open("scratch/test_voice.mp3", "wb") as f:
            f.write(response.content)
        print(f"Success! Real audio saved to: scratch/test_voice.mp3 (Size: {len(response.content)} bytes)")
    else:
        print(f"Error: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Exception: {e}")
