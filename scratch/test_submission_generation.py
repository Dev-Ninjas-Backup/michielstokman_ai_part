import requests
import time
import uuid
from app.core.db import SessionLocal
from app.model.liberation import LiberationDefinition, LiberationDayDefinition
from app.model.user import User
from app.model.billing import UserSubscription
from app.model.profile import UserProfile
from app.model.story import Story

BASE_URL = "http://localhost:8000"

print("==================================================")
print(" SUBMISSION GENERATION TEST (LIBERATION JOURNEY)")
print("==================================================")

# 1. Setup mock data
print("\n[1/4] Setting up mock LiberationDefinition in the database...")
db = SessionLocal()
try:
    # We need a user to assign as creator
    from app.model.user import User
    admin_user = db.query(User).first()
    if not admin_user:
        print("Error: No users found in database to act as creator.")
        exit(1)
        
    mock_sub = LiberationDefinition(
        id=uuid.uuid4(),
        journey_code=f"test-journey-{str(uuid.uuid4())[:8]}",
        title="7 Days to Letting Go",
        description="A journey to help release attachment and find peace.",
        total_days=7,
        created_by=admin_user.id,
        is_admin_created=False
    )
    db.add(mock_sub)
    db.commit()
    sub_id = str(mock_sub.id)
    print(f"Created mock submission with ID: {sub_id}")
finally:
    db.close()


# 2. Trigger Generation Directly
print("\n[2/4] Running Submission Generation worker directly...")
from app.services.service_ai import AIService
job_id = AIService.initiate_submission_generation(sub_id)
AIService.submission_generation_worker(job_id, sub_id)


# 4. Verify Database Days
print("\n[4/4] Verifying generated days in database...")
db = SessionLocal()
try:
    days = db.query(LiberationDayDefinition).filter(LiberationDayDefinition.definition_id == sub_id).order_by(LiberationDayDefinition.day_number).all()
    if len(days) == 7:
        print(f"Successfully found exactly 7 generated days!")
        for day in days:
            print(f"   Day {day.day_number}: {day.day_theme}")
    else:
        print(f"Expected 7 days but found {len(days)} in the database.")
finally:
    db.close()

print("\n==================================================")
print("TEST COMPLETE")
print("==================================================")
