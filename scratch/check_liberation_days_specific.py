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
    journeys = db.query(UserJourney).order_by(UserJourney.created_at.desc()).all()
    for j in journeys[:3]:
        print(f"\nJourney ID: {j.id}, Code: {j.journey_code}, Status: {j.status}, Definition ID: {j.definition_id}")
        # Look up definition
        d = j.definition
        if d:
            print(f"  Definition Code: {d.journey_code}, Title: {d.title}, Total Days: {d.total_days}")
            print(f"  Day Definitions count: {len(d.day_definitions)}")
            for dd in d.day_definitions:
                print(f"    Day {dd.day_number}: Theme={dd.day_theme}")
                print(f"      Exercise: {repr(dd.exercise_text)}")
                print(f"      Why: {repr(dd.why_text)}")
        else:
            print("  No associated definition found.")
finally:
    db.close()
