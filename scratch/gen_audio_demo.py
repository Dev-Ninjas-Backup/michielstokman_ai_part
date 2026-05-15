import requests
import os

# ElevenLabs configuration from your .env
API_KEY = "sk_6fcf19e8d1dead934525873b00a3f21ee0383ea699821f7a"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
MODEL_ID = "eleven_turbo_v2_5"

text = (
    "It was raining when I finally decided to leave. Not the dramatic storm I’d imagined, "
    "but a quiet, persistent drizzle that blurred the edges of the streetlights. "
    "My hands were trembling as I gripped the steering wheel, my knuckles white against "
    "the dark leather. For years, I’d played the role of the perfect wife, the one who "
    "always knew where the keys were and never forgot a birthday. But inside, I was hollow. "
    "I felt like a ghost haunting my own life. As I drove away, the smell of old coffee "
    "and damp wool filled the car, a strange comfort in the chaos. I didn’t know where "
    "I was going, only that for the first time in a decade, my breath felt like it belonged "
    "to me. I stopped at a red light and watched a single drop of rain slide down the "
    "windshield, perfectly clear. I wasn't happy, not yet. But I was here. I was real."
)

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

headers = {
    "Accept": "audio/mpeg",
    "Content-Type": "application/json",
    "xi-api-key": API_KEY
}

data = {
    "text": text,
    "model_id": MODEL_ID,
    "voice_settings": {
        "stability": 0.65,
        "similarity_boost": 0.8,
        "style": 0.3
    }
}

output_path = os.path.join("scratch", "confession_premium_demo.mp3")
print(f"Generating premium audio using ElevenLabs to {output_path}...")

response = requests.post(url, json=data, headers=headers)

if response.status_code == 200:
    with open(output_path, "wb") as f:
        f.write(response.content)
    print("Premium audio generation complete!")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
