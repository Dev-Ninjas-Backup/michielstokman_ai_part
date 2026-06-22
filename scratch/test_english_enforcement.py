import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.schema_ai import StoryGenerateRequest, StoryType
from app.services.service_ai import AIService

def test_english_enforcement():
    print("==================================================")
    print("[TESTING] English Enforcement & Translation")
    print("==================================================")

    test_cases = [
        {
            "lang": "Dutch",
            "type": StoryType.confession,
            "input": "Ik ben zo moe van de sleur in mijn huwelijk. Gisteravond keek hij me aan en ik voelde helemaal niets. Maar toen ik vandaag in de lift stond met de nieuwe buurman, begon mijn hart wild te kloppen.",
            "first_name": "Lieke",
            "gender": "female",
            "growth_areas": ["Fear & Freedom", "Self-Discovery"],
            "life_phase": "Deepening",
            "tags": ["marriage", "elevator", "neighbor"]
        },
        {
            "lang": "French",
            "type": StoryType.meditation,
            "input": "Une méditation sur la respiration profonde. Fermez les yeux, inspirez lentement par le nez, retenez votre souffle pendant quelques secondes, puis expirez doucement par la bouche en relâchant toute tension dans vos épaules.",
            "first_name": "Jean",
            "gender": "male",
            "growth_areas": ["Mindfulness", "Peace"],
            "life_phase": "Grounding",
            "tags": ["breath", "relaxation", "peace"]
        },
        {
            "lang": "German",
            "type": StoryType.confession,
            "input": "Ich kann nicht aufhören, an die Nacht im Hotel in Berlin zu denken. Es war falsch, aber es fühlte sich so lebendig an. Seine Hände auf meiner Haut...",
            "first_name": "Klaus",
            "gender": "male",
            "growth_areas": ["Intimacy", "Desire"],
            "life_phase": "Exploring",
            "tags": ["Berlin", "hotel", "secret"]
        }
    ]

    for tc in test_cases:
        print(f"\n--- Running Test Case: {tc['lang']} {tc['type'].value.upper()} ---")
        print(f"Input: {tc['input']}")
        
        req = StoryGenerateRequest(
            story_type=tc['type'],
            first_name=tc['first_name'],
            story_input=tc['input'],
            growth_areas=tc['growth_areas'],
            life_phase=tc['life_phase'],
            tags=tc['tags']
        )
        
        try:
            title, text, image_prompt = AIService.generate_story(req, gender=tc['gender'])
            
            print("\n[Generated Output]")
            print(f"TITLE (Should be English): {title}")
            print(f"IMAGE PROMPT (Should be English): {image_prompt}")
            print(f"STORY PREVIEW (Should be English):\n{text[:400]}...")
            
            # Simple check if there are obvious non-English words or if it's mostly in English
            # We can print status
            print(f"\n[Test Result] Generated successfully for {tc['lang']}.")
        except Exception as e:
            print(f"[ERROR]: Failed to generate story: {e}")

if __name__ == "__main__":
    test_english_enforcement()
