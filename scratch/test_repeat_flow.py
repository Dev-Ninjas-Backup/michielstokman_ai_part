import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.model.user import User
from app.model.profile import UserProfile
from app.model.billing import SubscriptionPlan, UserSubscription, SubscriptionStatus, SubscriptionInterval
from app.model.liberation import (
    LiberationDefinition,
    LiberationDayDefinition,
    UserJourney,
    UserJourneyStep,
    JourneyStatus,
    StepStatus,
    DefinitionStatus
)
from app.services.service_liberation import LiberationService

# Connect to database
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

print("==================================================")
print("RUNNING REPEAT JOURNEY FLOW UNIT TEST")
print("==================================================")

try:
    # 1. Fetch or create a test user
    user = db.query(User).filter(User.email == "test_repeater@example.com").first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email="test_repeater@example.com",
            password_hash="fakehashedpassword",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created test user: {user.email}")
    else:
        print(f"Using existing test user: {user.email}")

    # 2. Create a test liberation definition in catalog
    journey_code = "test_journey_code"
    definition = db.query(LiberationDefinition).filter(LiberationDefinition.journey_code == journey_code).first()
    if not definition:
        definition = LiberationDefinition(
            journey_code=journey_code,
            title="Test Journey",
            description="Testing restarting a journey",
            total_days=2,
            price_cents=0,
            created_by=user.id,
            moderation_status=DefinitionStatus.approved,
            is_active=True,
            is_admin_created=True
        )
        db.add(definition)
        db.commit()
        db.refresh(definition)
        print(f"Created catalog definition for: {journey_code}")

        # Add day definitions
        d1 = LiberationDayDefinition(definition_id=definition.id, day_number=1, day_theme="Theme 1", exercise_text="Ex 1", why_text="Why 1")
        d2 = LiberationDayDefinition(definition_id=definition.id, day_number=2, day_theme="Theme 2", exercise_text="Ex 2", why_text="Why 2")
        db.add_all([d1, d2])
        db.commit()
    else:
        print(f"Using existing catalog definition for: {journey_code}")

    # 3. Create mock subscription for the user to bypass the purchase gate
    plan_code = f"journey_{journey_code}"
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == plan_code).first()
    if not plan:
        plan = SubscriptionPlan(
            code=plan_code,
            name=f"Journey: {journey_code}",
            description="Test plan description",
            price_cents=0,
            interval_unit=SubscriptionInterval.year,
            is_active=True
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

    sub = db.query(UserSubscription).filter(
        UserSubscription.user_id == user.id,
        UserSubscription.plan_id == plan.id
    ).first()
    if not sub:
        sub = UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.active,
            provider_subscription_id="sub_test_repeat",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc)
        )
        db.add(sub)
        db.commit()
        print("Granted journey subscription to test user.")

    # 4. Cleanup old journeys for this test run
    db.query(UserJourneyStep).filter(
        UserJourneyStep.journey_id.in_(
            db.query(UserJourney.id).filter(
                UserJourney.user_id == user.id,
                UserJourney.journey_code == journey_code
            )
        )
    ).delete(synchronize_session=False)
    db.query(UserJourney).filter(UserJourney.user_id == user.id, UserJourney.journey_code == journey_code).delete()
    db.commit()

    # 5. Enroll in the journey (first run)
    print("\n[STEP 1/5] Enrolling user in journey...")
    status_dict = LiberationService.enroll(db, user.id, journey_code, total_days=2)
    assert status_dict["status"] == "active"
    assert status_dict["current_day"] == 1
    assert len(status_dict["steps"]) == 2
    assert status_dict["steps"][0]["status"] == "available"
    assert status_dict["steps"][1]["status"] == "locked"
    print("Enrolled successfully!")

    # 6. Complete Day 1
    print("\n[STEP 2/5] Completing Day 1...")
    # Generate Day 1
    LiberationService.generate_day(db, user.id, journey_code, day=1, morning_feeling="Tired but ready")
    # Complete Day 1
    res1 = LiberationService.complete_day(db, user.id, journey_code, day=1, energy_level=4.5, what_opened="Nothing yet", key_takeaway="Just start")
    assert res1["next_day_available"] is True
    print("Completed Day 1!")

    # 7. Complete Day 2
    print("\n[STEP 3/5] Completing Day 2 (Final Day)...")
    # Generate Day 2
    LiberationService.generate_day(db, user.id, journey_code, day=2, morning_feeling="Better")
    # Complete Day 2
    res2 = LiberationService.complete_day(db, user.id, journey_code, day=2, energy_level=5.0, what_opened="Heart opened", key_takeaway="Finish strong")
    assert res2["next_day_available"] is False

    # Check journey is completed
    status_dict = LiberationService.get_status(db, user.id, journey_code)
    assert status_dict["status"] == "completed"
    print("Completed full journey!")

    # 8. Try to repeat the journey
    print("\n[STEP 4/5] Repeating the completed journey...")
    repeated_status = LiberationService.repeat(db, user.id, journey_code)
    assert repeated_status["status"] == "active"
    assert repeated_status["current_day"] == 1
    assert repeated_status["steps"][0]["status"] == "available"
    assert repeated_status["steps"][1]["status"] == "locked"
    
    # Verify DB records are cleared
    journey = db.query(UserJourney).filter(UserJourney.user_id == user.id, UserJourney.journey_code == journey_code).first()
    assert journey.status == JourneyStatus.active
    for step in journey.steps:
        if step.day_number == 1:
            assert step.status == StepStatus.available
        else:
            assert step.status == StepStatus.locked
        assert step.morning_feeling is None
        assert step.ai_greeting is None
        assert step.ai_exercise_text is None
        assert step.ai_why_text is None
        assert step.reflection_opened is None
        assert step.reflection_takeaway is None
        assert step.completed_at is None
    print("Repeated successfully! All steps and status reset correctly.")

    # 9. Clean up database
    print("\n[STEP 5/5] Cleaning up test data...")
    db.query(UserJourneyStep).filter(UserJourneyStep.journey_id == journey.id).delete()
    db.query(UserJourney).filter(UserJourney.id == journey.id).delete()
    db.query(UserSubscription).filter(UserSubscription.id == sub.id).delete()
    db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan.id).delete()
    db.query(LiberationDayDefinition).filter(LiberationDayDefinition.definition_id == definition.id).delete()
    db.query(LiberationDefinition).filter(LiberationDefinition.id == definition.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    db.commit()
    print("Cleanup complete!")

    print("\nALL TESTS PASSED SUCCESSFULLY!")

except Exception as e:
    print(f"TEST FAILED: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
