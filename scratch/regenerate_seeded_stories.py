import uuid
from sqlalchemy.orm import Session

# Import models & modules
from app.model.user import User
from app.model.profile import UserProfile
from app.model.billing import UserSubscription, SubscriptionPlan, PaymentTransaction
from app.model.credit import UserCredit
from app.model.feedback import StoryFeedback
from app.model.guest_session import GuestSession
from app.model.liberation import LiberationDefinition, LiberationDayDefinition, UserJourney, UserJourneyStep
from app.model.cover_image import CoverImage

from app.core.db import SessionLocal
from app.model.story import Story
from app.core.llm import generate_voice_elevenlabs, save_audio
from app.utils.media import get_mp3_duration

def main():
    db: Session = SessionLocal()
    # Selected story IDs that we just added
    story_ids = [
        "841f13fa-f36c-4cfd-a049-f2fbc8c47b2a", # Lars
        "58cefc57-361a-4928-8607-7c5e16859d5b", # Joanna
        "f5a287dc-5eaa-4dd5-8ba1-4dac9276371b", # Jonas
        "97967128-255d-4c2b-9e3c-fca837b0d7c8", # Desiree
        "f34dd532-1895-4505-a68f-54a6205fe583"  # Jasna
    ]
    
    try:
        for s_id in story_ids:
            story = db.query(Story).filter(Story.id == uuid.UUID(s_id)).first()
            if not story:
                print(f"Story ID {s_id} not found in DB!")
                continue
                
            print(f"\nRegenerating Story: {story.title} ({story.first_name} | Voice: {story.voice_name})")
            print("Generating voice audio with new slow-pacing/pauses via ElevenLabs...")
            audio_bytes = generate_voice_elevenlabs(text=story.story_text, voice_id=story.voice_name)
            
            print("Saving new audio file...")
            audio_path = save_audio(audio_bytes)
            print(f"New audio path: {audio_path}")
            
            # Calculate duration
            duration = int(get_mp3_duration(audio_bytes))
            print(f"New audio duration: {duration} seconds")
            
            # Update story
            story.audio_path = audio_path
            story.audio_duration_seconds = duration
            db.commit()
            db.refresh(story)
            print(f"Successfully updated Story ID {story.id} with slow audio!")
            
    except Exception as e:
        print(f"Error during regeneration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
