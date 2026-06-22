import os
import re
import random
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

# Import backend modules
from app.core.db import SessionLocal
from app.model.user import User
from app.model.profile import UserProfile
from app.model.billing import UserSubscription, SubscriptionPlan, PaymentTransaction
from app.model.credit import UserCredit
from app.model.feedback import StoryFeedback
from app.model.guest_session import GuestSession
from app.model.liberation import LiberationDefinition, LiberationDayDefinition, UserJourney, UserJourneyStep
from app.model.cover_image import CoverImage
from app.model.story import Story, StoryType, GenerationStatus, ModerationStatus
from app.core.llm import generate_voice_elevenlabs, save_audio
from app.utils.media import get_mp3_duration

def extract_meditations():
    with open("scratch/meditations_full_text.txt", "r", encoding="utf-8") as f:
        text = f.read()
        
    blocks = re.split(r'(?i)\bTitle:?\s*', text)
    
    # Truncate Block 6 at page 62
    block_6 = blocks[6].split("--- PAGE 62 ---")[0].strip()
    
    med_blocks = [
        blocks[1].strip(),
        blocks[2].strip(),
        blocks[3].strip(),
        blocks[4].strip(),
        blocks[5].strip(),
        block_6
    ]
    return med_blocks

def parse_meditation_block(block_text, idx):
    lines = [l.strip() for l in block_text.split("\n")]
    
    title = ""
    for l in lines:
        if l:
            title = l
            break
            
    author_match = re.search(r'(?i)Author:\s*([A-Za-z]+)', block_text)
    author = author_match.group(1).strip() if author_match else ""
    if not author:
        if "Emma" in block_text:
            author = "Emma"
        elif "Elena" in block_text:
            author = "Elena"
        elif "Marc" in block_text:
            author = "Marc"
            
    age_match = re.search(r'(?i)Age:\s*(\d+)', block_text)
    age = int(age_match.group(1)) if age_match else None
    
    gender_match = re.search(r'(?i)Gender(?:\s*&\s*Sexual\s*orientation)?:\s*([A-Za-z]+)', block_text)
    gender_str = gender_match.group(1).lower() if gender_match else "female"
    gender = "female" if "woman" in gender_str or "female" in gender_str else "male"
    
    country_city_match = re.search(r'(?i)Country\s*/\s*City:\s*([^/\n]+)\s*/\s*([^\n]+)', block_text)
    if country_city_match:
        country = country_city_match.group(1).strip()
        city = country_city_match.group(2).strip()
    else:
        fallback_match = re.search(r'(?i)Author:\s*[A-Za-z]+,\s*\d+\s*years\s*old,\s*([^,\n]+),\s*([^\n]+)', block_text)
        if fallback_match:
            city = fallback_match.group(1).strip()
            country = fallback_match.group(2).strip()
        else:
            country = "France" if author in ["Emma", "Marc"] else "Canada"
            city = "Nice" if author in ["Emma", "Marc"] else "Vancouver"
            
    # Parse Life Phase / Situation
    life_phase_str = ""
    lp_match = re.search(r'(?i)Life\s*(?:phase|situation):\s*([^\n]+)', block_text)
    if lp_match:
        life_phase_str = lp_match.group(1).strip()
        # Find if it continues on subsequent lines before One-sentence essence / Relationship status / Growth Area
        start_idx = block_text.find(lp_match.group(0))
        lines_after = block_text[start_idx:].split("\n")
        additional_lines = []
        for la in lines_after[1:]:
            la_strip = la.strip()
            if not la_strip:
                continue
            if any(la_strip.lower().startswith(prefix) for prefix in ["relationship status", "one-sentence", "growth area", "high intensity", "month:", "age:", "gender:"]):
                break
            additional_lines.append(la_strip)
        if additional_lines:
            life_phase_str += " " + " ".join(additional_lines)
            
    growth_areas = []
    ga1_match = re.search(r'(?i)Growth\s*Area\s*1:\s*([^\n]+)', block_text)
    if ga1_match:
        val = ga1_match.group(1).strip()
        if val and val != "—" and val != "-":
            growth_areas.append(val)
    ga2_match = re.search(r'(?i)Growth\s*Area\s*2:\s*([^\n]+)', block_text)
    if ga2_match:
        val = ga2_match.group(1).strip()
        if val and val != "—" and val != "-":
            growth_areas.append(val)
            
    if not growth_areas:
        if idx == 1:
            growth_areas = ["Fear & Freedom", "Desire & Relationship"]
        else:
            growth_areas = ["Fear & Freedom"]
            
    high_intensity = False
    hi_match = re.search(r'(?i)High\s*Intensity\s*Toggle:\s*([A-Za-z]+)', block_text)
    if hi_match:
        high_intensity = hi_match.group(1).lower() in ["on", "true", "yes"]
        
    script_start_idx = -1
    for i, l in enumerate(lines):
        if "full meditation script" in l.lower() or "longer meditation" in l.lower():
            script_start_idx = i + 1
            break
            
    if script_start_idx == -1:
        for i, l in enumerate(lines):
            if "welcome" in l.lower():
                script_start_idx = i
                break
                
    if script_start_idx == -1:
        script_start_idx = 15
        
    script_lines = lines[script_start_idx:]
    
    cleaned_script_lines = []
    for l in script_lines:
        l_strip = l.strip()
        if not l_strip:
            cleaned_script_lines.append("")
            continue
        if l_strip.startswith("--- PAGE") or re.match(r'^\d+\s*---$', l_strip) or re.match(r'^---\s*\d+$', l_strip):
            continue
        cleaned_script_lines.append(l)
        
    script_text = "\n".join(cleaned_script_lines).strip()
    
    # Trim metadata headers by finding first welcome/take seat
    match_start = re.search(r'(?i)\b(?:welcome|take\s+a\s+comfortable\s+seat)\b', script_text)
    if match_start:
        script_text = script_text[match_start.start():].strip()
        
    return {
        "title": title.strip(" -–"),
        "first_name": author,
        "age": age,
        "gender": gender,
        "country": country,
        "city": city,
        "growth_areas": growth_areas,
        "high_intensity": high_intensity,
        "life_phase": life_phase_str,
        "story_text": script_text
    }

def main():
    print("Loading and parsing the 6 meditations...")
    blocks = extract_meditations()
    
    # Connect to database
    db: Session = SessionLocal()
    try:
        for idx, block_text in enumerate(blocks):
            data = parse_meditation_block(block_text, idx + 1)
            title = data["title"]
            
            print(f"\nProcessing Meditation {idx+1}: {title} ({data['first_name']})")
            
            # Delete if exists to re-seed fresh with new alignment/voices
            existing_story = db.query(Story).filter(Story.title == title).first()
            if existing_story:
                print(f"Found existing story for '{title}'. Deleting to re-seed fresh...")
                db.delete(existing_story)
                db.commit()
                
            # Resolve voice selection
            if data["gender"] == "male":
                voice_name = "Calen"
            else:
                # Mix them up deterministically to use all female voices
                voice_mapping = {
                    1: "Victoria",   # Emma (France)
                    2: "Sophia",     # Elena (Canada)
                    3: "Charlotte",  # Elena (Canada)
                    5: "Chapter1",   # Elena (Canada)
                    6: "Anja"        # Elena (Portugal)
                }
                voice_name = voice_mapping.get(idx + 1, "Sophia")
                
            print(f"Generating voice audio using ElevenLabs voice: {voice_name}...")
            
            # Generate audio and word-level alignments
            audio_bytes, alignment = generate_voice_elevenlabs(
                text=data["story_text"],
                voice_id=voice_name,
                story_type="meditation",
                return_timestamps=True
            )
            
            print("Saving audio...")
            audio_path = save_audio(audio_bytes)
            print(f"Audio saved to: {audio_path}")
            
            duration = int(get_mp3_duration(audio_bytes))
            print(f"Audio duration: {duration} seconds")
            
            # Random seed social metrics
            views = random.randint(150, 450)
            reflections = random.randint(50, 150)
            shares = random.randint(20, 80)
            pulse = round(random.uniform(88.0, 97.5), 1)
            
            story_db = Story(
                story_type=StoryType.meditation,
                job_id=f"manual-seed-meditation-{uuid.uuid4().hex[:12]}",
                generation_status=GenerationStatus.completed,
                moderation_status=ModerationStatus.approved,
                title=title,
                first_name=data["first_name"],
                story_text=data["story_text"],
                audio_path=audio_path,
                voice_name=voice_name,
                audio_duration_seconds=duration,
                alignment=alignment,
                views_count=views,
                shares_count=shares,
                reflections_count=reflections,
                pulse_score=pulse,
                growth_areas=data["growth_areas"],
                life_phase=data["life_phase"],
                tags=["meditation", data["country"], data["city"]],
                high_intensity=data["high_intensity"]
            )
            db.add(story_db)
            db.commit()
            db.refresh(story_db)
            print(f"Successfully seeded Story ID {story_db.id}!")
            
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
