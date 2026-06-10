import os
import re
import random
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

# Import backend modules
from app.model.user import User
from app.model.profile import UserProfile
from app.model.billing import UserSubscription, SubscriptionPlan, PaymentTransaction
from app.model.credit import UserCredit
from app.model.feedback import StoryFeedback
from app.model.guest_session import GuestSession
from app.model.liberation import LiberationJourney, TransformationStep, UserStepProgress
from app.model.cover_image import CoverImage
from app.core.db import SessionLocal
from app.model.story import Story, StoryType, GenerationStatus, ModerationStatus
from app.core.llm import generate_voice_elevenlabs, save_audio
from app.utils.media import get_mp3_duration

def clean_narrative(story_text: str) -> str:
    lines = [l.strip() for l in story_text.split("\n") if l.strip()]
    narrative_lines = []
    
    # Skip title and metadata lines at the beginning
    for line in lines[1:]:
        if line.startswith("**") and any(x in line for x in ["Story by", "M /", "F /", "hetero", "bi", "trans", "married", "divorced", "Word count"]):
            continue
        elif line.startswith("(") and "Word count" in line:
            continue
        elif any(line.endswith(suffix) for suffix in ["– 18–25", "– 25–35", "– 35–47", "– 47–60", "– 60+"]):
            continue
        elif any(x in line for x in ["Swingen", "swingen", "Healthy and longevity"]):
            continue
        else:
            narrative_lines.append(line)
            
    return "\n\n".join(narrative_lines)

def get_selected_stories():
    with open("scratch/docx_content.txt", "r", encoding="utf-8") as f:
        text = f.read()
        
    story_matches = list(re.finditer(r"\*\*Story (\d+)\b", text))
    
    # Mapping indices of matches to configuration
    # Match indices: 1 (Story 28), 4 (Story 132), 5 (Story 136), 7 (Story 201), 8 (Story 204)
    story_configs = [
        {"match_idx": 1, "title": "The Night She Took the Lead", "name": "Lars", "voice": "Calen", "gender": "male"},
        {"match_idx": 4, "title": "Back to the Current", "name": "Joanna", "voice": "Chapter1", "gender": "female"},
        {"match_idx": 5, "title": "Contact with the Trees", "name": "Jonas", "voice": "Calen", "gender": "male"},
        {"match_idx": 7, "title": "Growing Toward the Light", "name": "Desiree", "voice": "Anja", "gender": "female"},
        {"match_idx": 8, "title": "The First Time We Shared", "name": "Jasna", "voice": "Sophia", "gender": "female"}
    ]
    
    extracted = []
    for conf in story_configs:
        idx = conf["match_idx"]
        start = story_matches[idx].start()
        end = story_matches[idx+1].start() if idx+1 < len(story_matches) else len(text)
        story_raw = text[start:end]
        
        narrative = clean_narrative(story_raw)
        extracted.append({
            "title": conf["title"],
            "first_name": conf["name"],
            "voice_name": conf["voice"],
            "gender": conf["gender"],
            "story_text": narrative
        })
    return extracted

def main():
    print("Extracting and cleaning the 5 selected stories...")
    stories = get_selected_stories()
    
    db: Session = SessionLocal()
    try:
        for s in stories:
            print(f"\nProcessing Story: {s['title']} ({s['first_name']} | Voice: {s['voice_name']})")
            print(f"Text length: {len(s['story_text'])} chars")
            print(f"Sample: {s['story_text'][:150]}...")
            
            # Generate Audio
            print("Generating voice audio via ElevenLabs...")
            audio_bytes = generate_voice_elevenlabs(text=s['story_text'], voice_id=s['voice_name'])
            
            print("Saving audio file...")
            audio_path = save_audio(audio_bytes)
            print(f"Audio path: {audio_path}")
            
            # Calculate duration
            duration = int(get_mp3_duration(audio_bytes))
            print(f"Audio duration: {duration} seconds")
            
            # Seed social metrics
            views = random.randint(150, 450)
            reflections = random.randint(50, 150)
            shares = random.randint(20, 80)
            pulse = round(random.uniform(88.0, 97.5), 1)
            
            # Insert into database
            story_db = Story(
                story_type=StoryType.confession,
                job_id=f"manual-seed-{uuid.uuid4().hex[:12]}",
                generation_status=GenerationStatus.completed,
                moderation_status=ModerationStatus.approved,
                title=s['title'],
                first_name=s['first_name'],
                story_text=s['story_text'],
                audio_path=audio_path,
                voice_name=s['voice_name'],
                audio_duration_seconds=duration,
                views_count=views,
                shares_count=shares,
                reflections_count=reflections,
                pulse_score=pulse,
            )
            db.add(story_db)
            db.commit()
            db.refresh(story_db)
            print(f"Successfully added Story ID {story_db.id} to the database!")
            
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
