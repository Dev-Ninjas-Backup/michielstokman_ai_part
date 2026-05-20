from app.core.db import SessionLocal
from app.model.user import User
from app.model.billing import UserSubscription, SubscriptionPlan, PaymentTransaction
from app.model.cover_image import CoverImage
from app.model.credit import UserCredit
from app.model.feedback import StoryFeedback
from app.model.profile import UserProfile
from app.model.story import Story
from app.model.liberation import LiberationDefinition, LiberationDayDefinition, UserJourney, UserJourneyStep

db = SessionLocal()
try:
    print("--- User Journeys ---")
    journeys = db.query(UserJourney).all()
    for j in journeys:
        print(f"ID: {j.id}, User ID: {j.user_id}, Code: {j.journey_code}, Status: {j.status}, Definition ID: {j.definition_id}")
        
    print("\n--- Definitions ---")
    defs = db.query(LiberationDefinition).all()
    for d in defs:
        print(f"ID: {d.id}, Code: {d.journey_code}, Title: {d.title}, Active: {d.is_active}, Admin Created: {d.is_admin_created}")
        for dd in d.day_definitions:
            print(f"  Day {dd.day_number}: Theme={dd.day_theme}")
            print(f"    Exercise: {dd.exercise_text[:60] if dd.exercise_text else None}...")
            print(f"    Why: {dd.why_text[:60] if dd.why_text else None}...")

    print("\n--- User Journey Steps ---")
    steps = db.query(UserJourneyStep).all()
    for s in steps:
        print(f"Journey ID: {s.journey_id}, Day: {s.day_number}, Status: {s.status}")
        print(f"  Greeting: {s.ai_greeting[:60] if s.ai_greeting else None}...")
        print(f"  Exercise: {s.ai_exercise_text[:60] if s.ai_exercise_text else None}...")
finally:
    db.close()
