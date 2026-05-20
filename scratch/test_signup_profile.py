import sys
import os
import uuid

# Force stdout to use utf-8
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.core.db import SessionLocal
from app.model.user import User
from app.model.profile import UserProfile

print("==================================================")
print("TESTING SIGNUP PROFILE PLACEHOLDER CREATION")
print("==================================================")

client = TestClient(app)
db = SessionLocal()

# Cleanup any previous test user
test_email = "placeholder_tester@example.com"
db.query(UserProfile).filter(
    UserProfile.user_id.in_(
        db.query(User.id).filter(User.email == test_email)
    )
).delete(synchronize_session=False)
db.query(User).filter(User.email == test_email).delete()
db.commit()

try:
    # 1. Post to signup
    signup_payload = {
        "email": test_email,
        "password": "Password123!"
    }
    print("Sending signup request...")
    response = client.post("/v1/signup", json=signup_payload)
    print(f"Signup response status: {response.status_code}")
    assert response.status_code == 201, f"Expected 201, got {response.status_code}"
    
    signup_json = response.json()
    assert signup_json["success"] is True
    access_token = signup_json["access_token"]
    print("Signup succeeded and token received.")

    # 2. Get profile using the token
    print("Sending get profile request...")
    headers = {"Authorization": f"Bearer {access_token}"}
    profile_response = client.get("/v1/auth/profile", headers=headers)
    print(f"Profile response status: {profile_response.status_code}")
    print(f"Profile response body: {profile_response.text}")
    assert profile_response.status_code == 200, f"Expected 200, got {profile_response.status_code}"
    
    profile_json = profile_response.json()
    assert profile_json["success"] is True
    data = profile_json["data"]
    
    # 3. Assert all fields have dummy values
    print("Verifying all fields have correct placeholder values...")
    assert data["true_name"] == ""
    assert data["age"] == 0
    assert data["country"] == ""
    assert data["city"] == ""
    assert data["height"] == ""
    assert data["education"] == ""
    assert data["annual_income"] == ""
    assert data["gender"] == ""
    assert data["sexual_orientation"] == ""
    assert data["life_phase"] == ""
    assert data["bio"] == ""
    assert data["profile_image_url"] == ""
    assert data["slider_desire_relationship"] == 0
    assert data["slider_life_purpose"] == 0
    assert data["slider_career_money"] == 0
    assert data["slider_true_self"] == 0
    assert data["slider_sexuality_life_energy"] == 0
    assert data["slider_fear_freedom"] == 0
    assert data["slider_health_body"] == 0
    assert data["slider_enlightenment"] == 0

    print("ALL VERIFICATIONS PASSED SUCCESSFULLY!")

finally:
    # Cleanup test user and profile
    print("Cleaning up test records from database...")
    db.query(UserProfile).filter(
        UserProfile.user_id.in_(
            db.query(User.id).filter(User.email == test_email)
        )
    ).delete(synchronize_session=False)
    db.query(User).filter(User.email == test_email).delete()
    db.commit()
    db.close()
