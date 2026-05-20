import sys
import os
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

from sqlalchemy import func
from app.core.db import SessionLocal
from app.model.user import User
from app.model.story import Story, StoryType, GenerationStatus
from app.model.liberation import UserJourney, JourneyStatus
from app.model.billing import UserSubscription, PaymentTransaction, SubscriptionPlan
from app.model.feedback import StoryFeedback
from app.model.profile import UserProfile
from app.model.credit import UserCredit
from app.model.cover_image import CoverImage
from app.data.admin_dashboard import get_figma_dashboard_stats

def run_test():
    print("==================================================")
    print("RUNNING ADMIN DASHBOARD METRICS ROUNDING TEST")
    print("==================================================")
    
    db = SessionLocal()
    user_id = None
    journey_ids = []
    story_ids = []
    
    try:
        # 1. Create a test user
        user = User(
            id=uuid.uuid4(),
            email=f"admin_test_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        print(f"Created test user: {user.email}")
        
        # 2. Create 7 UserJourneys (3 completed, 4 active) to get a completion rate with many decimals (3/7 * 100 = 42.85714...)
        print("Creating test journeys...")
        for i in range(7):
            status = JourneyStatus.completed if i < 3 else JourneyStatus.active
            j = UserJourney(
                id=uuid.uuid4(),
                user_id=user_id,
                journey_code="liberation_journey",
                status=status
            )
            db.add(j)
            journey_ids.append(j.id)
            
        # 3. Create stories with views and pulse score
        print("Creating test stories...")
        s1 = Story(
            id=uuid.uuid4(),
            story_type=StoryType.confession,
            generation_status=GenerationStatus.completed,
            views_count=100,
            pulse_score=8.57,  # decimals
            user_id=user_id
        )
        s2 = Story(
            id=uuid.uuid4(),
            story_type=StoryType.confession,
            generation_status=GenerationStatus.completed,
            views_count=150,
            pulse_score=9.12,  # decimals
            user_id=user_id
        )
        db.add(s1)
        db.add(s2)
        story_ids.extend([s1.id, s2.id])
        
        db.commit()
        
        # 4. Fetch admin stats
        print("Fetching Figma dashboard stats...")
        stats = get_figma_dashboard_stats(db)
        
        # Verify top stats
        top_stats = stats["top_stats"]
        print(f"Views Value: {top_stats['views']['value']}")
        print(f"Resonance Value: {top_stats['resonance']['value']}")
        print(f"Completion Value: {top_stats['completion']['value']}%")
        print(f"Shares Value: {top_stats['shares']['value']}")
        
        # Expected completion dynamically from DB
        total_j = db.query(UserJourney).count()
        completed_j = db.query(UserJourney).filter(UserJourney.status == JourneyStatus.completed).count()
        expected_completion = round((completed_j / total_j * 100.0), 2) if total_j > 0 else 0.0
        # Expected pulse dynamically from DB
        total_pulse = db.query(func.avg(Story.pulse_score)).scalar()
        expected_pulse = round(float(total_pulse or 0.0), 1)
        
        assert top_stats['completion']['value'] == expected_completion, f"Expected {expected_completion}, got {top_stats['completion']['value']}"
        assert top_stats['resonance']['value'] == expected_pulse, f"Expected {expected_pulse}, got {top_stats['resonance']['value']}"
        
        print("\nADMIN METRICS TESTS PASSED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if user_id or journey_ids or story_ids:
            print("\nCleaning up database...")
            for s_id in story_ids:
                db.query(Story).filter(Story.id == s_id).delete()
            for j_id in journey_ids:
                db.query(UserJourney).filter(UserJourney.id == j_id).delete()
            if user_id:
                db.query(User).filter(User.id == user_id).delete()
            db.commit()
            print("Cleanup complete!")
        db.close()

if __name__ == "__main__":
    run_test()
