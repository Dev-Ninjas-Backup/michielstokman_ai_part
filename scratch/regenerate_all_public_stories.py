import uuid
import re
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

VOICE_MAP = {
    # 5 Seeded Stories
    "841f13fa-f36c-4cfd-a049-f2fbc8c47b2a": ("Calen", "The Night She Took the Lead"),
    "58cefc57-361a-4928-8607-7c5e16859d5b": ("Chapter1", "Back to the Current"),
    "f5a287dc-5eaa-4dd5-8ba1-4dac9276371b": ("Calen", "Contact with the Trees"),
    "97967128-255d-4c2b-9e3c-fca837b0d7c8": ("Anja", "Growing Toward the Light"),
    "f34dd532-1895-4505-a68f-54a6205fe583": ("Sophia", "The First Time We Shared"),
    
    # 6 Previous Stories (to update with new voices)
    "69a45f44-befd-412f-a6fd-fde4762290f6": ("Anja", "Anna – 22, rood haar, 164 cm, Wales, kerstavond"),
    "2f902380-3569-43e2-a24a-c20fa735a9d8": ("Calen", "Ik ben 39, advocaat, en die nacht in november in Warschau brak er iets open dat nooit meer dichtgaat"),
    "1f181832-fd2d-467c-894f-e79ebe832472": ("Calen", "Ik ben 38, getrouwd, altijd de nette collega – en die nacht in oktober brak Sofie me helemaal open"),
    "b60a97de-c271-491f-8758-0a917ba7a9be": ("Sophia", "Ik ben Brigitte, 42, getrouwd, en die nacht op een techno-feest in Berlijn kreeg ik eindelijk die paar minuten die ik al maanden wilde"),
    "04000879-b2bb-45c3-beea-776495b1747b": ("Chapter1", "Ik ben Audrey, 55, uit Bordeaux, en die nacht in Le Marais werd ik eindelijk weer vrouw"),
    "fae0f5f7-1fb9-49e2-bf53-275d0e31dee2": ("Anja", "Ik ben 32, stewardess , wonend te Barcelona, en die nacht in oktober 2025 werd ik eindelijk weer helemaal mezelf")
}

def strip_leading_date_and_markdown(text: str) -> str:
    if not text:
        return ""
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    lines = text.split("\n")
    cleaned_lines = []
    
    skip_header = True
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not skip_header:
                cleaned_lines.append(line)
            continue
            
        if skip_header:
            cleaned_stripped = stripped.replace("**", "").replace("*", "").strip()
            # Check if this line is a date header (e.g. "March 2026")
            if any(m in cleaned_stripped for m in months) and any(c.isdigit() for c in cleaned_stripped):
                continue
            else:
                skip_header = False
        
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines).strip()

def main():
    from app.core.config import settings
    print(f"DEBUG: settings.ELEVENLABS_API_KEY = {settings.ELEVENLABS_API_KEY}")
    db: Session = SessionLocal()
    try:
        for s_id, (voice_name, title_expected) in VOICE_MAP.items():
            story = db.query(Story).filter(Story.id == uuid.UUID(s_id)).first()
            if not story:
                print(f"Story ID {s_id} not found in DB!")
                continue
                
            print(f"\n==========================================")
            print(f"Processing Story: {story.title} -> Voice: {voice_name}")
            
            # 1. Clean story text (remove leading date headers)
            original_text = story.story_text or ""
            cleaned_text = strip_leading_date_and_markdown(original_text)
            
            print(f"Original text length: {len(original_text)} | Cleaned text length: {len(cleaned_text)}")
            print(f"Cleaned start sample: {repr(cleaned_text[:150])}")
            
            # 2. Call ElevenLabs TTS to generate the high-fidelity audio
            print("Generating voice audio via ElevenLabs with timestamps...")
            audio_bytes, alignment = generate_voice_elevenlabs(text=cleaned_text, voice_id=voice_name, return_timestamps=True)
            
            # 3. Save audio file locally
            print("Saving audio file...")
            audio_path = save_audio(audio_bytes)
            print(f"Audio path: {audio_path}")
            
            # 4. Calculate exact duration
            duration = int(get_mp3_duration(audio_bytes))
            print(f"Audio duration: {duration} seconds")
            
            # 5. Update DB
            story.story_text = cleaned_text
            story.voice_name = voice_name
            story.audio_path = audio_path
            story.audio_duration_seconds = duration
            story.alignment = alignment
            db.commit()
            db.refresh(story)
            print(f"Successfully updated Story ID {story.id} in database!")
            
    except Exception as e:
        print(f"Error during regeneration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
