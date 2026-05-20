import requests
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

key = os.getenv("ELEVENLABS_API_KEY")
r = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
voices = r.json().get("voices", [])
print(f"Found {len(voices)} voices:\n")
for v in voices:
    labels = v.get("labels", {})
    desc = labels.get("description", "")
    gender = labels.get("gender", "")
    print(f"  {v['voice_id']}  |  {v['name']}  |  {gender}  |  {desc}")
