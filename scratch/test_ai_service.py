import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.service_ai import AIService
from app.schemas.schema_ai import ResonanceRequest, StoryGenerateRequest
from app.model.story import StoryType

print("==================================================")
print("[TESTING] AI SERVICE (GROQ)")
print("==================================================")

# 1. Test Resonance Question Generation
print("\n[1/2] Testing Resonance Question Generation...")
try:
    res_req = ResonanceRequest(
        track_id="track_test_123",
        touch_score=8,
        sliders={"anxiety": 7, "hope": 4}
    )
    res_resp = AIService.generate_resonance_question(res_req)
    print("[SUCCESS]")
    print(f"Generated Question: {res_resp.journaling_question}")
except Exception as e:
    print(f"[FAILED]: {e}")

# 2. Test Story Generation
print("\n[2/2] Testing Story Generation (Confession)...")
try:
    story_req = StoryGenerateRequest(
        story_type=StoryType.confession,
        story_input="I feel overwhelmed by the expectations people have of me.",
        title="Letting go of perfectionism",
        first_name="Sophia"
    )
    # We call generate_story directly to bypass the database job/worker logic for this test
    title, story_text, image_prompt = AIService.generate_story(story_req)
    print("[SUCCESS]")
    print(f"Generated Title: {title}")
    print(f"Generated Image Prompt: {image_prompt}")
    print(f"Generated Story:\n{story_text[:500]}...\n[truncated for length]")
except Exception as e:
    print(f"[FAILED]: {e}")

print("\n==================================================")
print("TEST COMPLETE")
print("==================================================")
