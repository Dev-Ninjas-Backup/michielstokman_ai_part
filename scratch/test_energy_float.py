import sys
import os
from pathlib import Path

# Force stdout to use utf-8 to prevent emoji encoding errors on Windows terminals
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.core.db import get_db
from app.model.user import User
from app.model.liberation import UserJourney, UserJourneyStep, StepStatus, JourneyStatus
from app.api.deps import get_current_user

client = TestClient(app)

db_gen = get_db()
db = next(db_gen)

test_user = db.query(User).first()
print(f"Using test user: {test_user.email if test_user else 'None'}")

if test_user:
    from app.model.billing import SubscriptionPlan, UserSubscription, SubscriptionInterval, SubscriptionStatus
    # Ensure plan exists
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == "journey_vitality").first()
    if not plan:
        plan = SubscriptionPlan(
            code="journey_vitality",
            name="Vitality Premium Journey",
            price_cents=999,
            interval_unit=SubscriptionInterval.year,
            interval_count=1
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        print("Created mock SubscriptionPlan 'journey_vitality'.")
        
    # Ensure user has active subscription
    sub = db.query(UserSubscription).filter(
        UserSubscription.user_id == test_user.id,
        UserSubscription.plan_id == plan.id
    ).first()
    if not sub:
        sub = UserSubscription(
            user_id=test_user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.active
        )
        db.add(sub)
        db.commit()
        print("Created active UserSubscription for test user.")
    
    # Let's ensure a journey exists for this user so we can test completing a step
    journey = db.query(UserJourney).filter(UserJourney.user_id == test_user.id).first()
    if not journey:
        journey = UserJourney(
            user_id=test_user.id,
            journey_code="vitality",
            total_days=7,
            status=JourneyStatus.active
        )
        db.add(journey)
        db.flush()
        
        # Create at least step 1
        step = UserJourneyStep(
            journey_id=journey.id,
            day_number=1,
            status=StepStatus.available,
            day_theme="Awakening"
        )
        db.add(step)
        db.commit()
        db.refresh(journey)
        print("Created mock UserJourney and Step 1.")
    else:
        # Ensure Step 1 is available/locked but not completed, or just reset its status to available
        step = db.query(UserJourneyStep).filter(
            UserJourneyStep.journey_id == journey.id,
            UserJourneyStep.day_number == 1
        ).first()
        if not step:
            step = UserJourneyStep(
                journey_id=journey.id,
                day_number=1,
                status=StepStatus.available,
                day_theme="Awakening"
            )
            db.add(step)
            db.commit()
        else:
            step.status = StepStatus.available
            db.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user

try:
    print("\n--- 1. Testing Completing Day with Float Energy Level (POST /v1/liberation/{code}/day/1/complete) ---")
    
    payload = {
        "energy_level": 8.5,  # float value!
        "what_opened": "A lot of peace and clarity opened up.",
        "key_takeaway": "Daily breathing brings deep presence."
    }
    
    response = client.post(
        f"/v1/liberation/{journey.journey_code}/day/1/complete",
        json=payload
    )
    
    print(f"Status Code: {response.status_code}")
    response_json = response.json()
    print(f"Response: {response_json}")
    
    assert response.status_code == 200
    print("[SUCCESS] Day complete submission with float energy level succeeded!")

    print("\n--- 2. Testing Day Detail Fetch (GET /v1/liberation/{code}/day/1) ---")
    response = client.get(f"/v1/liberation/{journey.journey_code}/day/1")
    print(f"Status Code: {response.status_code}")
    response_json = response.json()
    print(f"Response data: {response_json['data']}")
    
    assert response.status_code == 200
    assert response_json["data"]["energy_level_after"] == 8.5
    print(f"[SUCCESS] Retrieved float energy level successfully! Value: {response_json['data']['energy_level_after']}")

finally:
    # Cleanup dependency overrides
    app.dependency_overrides.clear()
