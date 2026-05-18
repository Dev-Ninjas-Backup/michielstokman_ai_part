import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.core.db import get_db
from app.core.config import settings
from app.model.user import User
from app.api.deps import get_current_user

client = TestClient(app)

# Create a mock user for bypass or inject via dependency override
db_gen = get_db()
db = next(db_gen)

test_user = db.query(User).first()
print(f"Using test user: {test_user.email if test_user else 'None'}")

if test_user:
    from app.model.profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == test_user.id).first()
    if not profile:
        profile = UserProfile(
            user_id=test_user.id,
            true_name="Test User",
            age=30,
            country="USA",
            city="New York"
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        print("Created mock UserProfile for test user.")
    app.dependency_overrides[get_current_user] = lambda: test_user

try:
    print("\n--- 1. Creating 1x1 Pixel Dummy Image ---")
    dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    
    # Temporarily unset S3 settings in memory to force fallback
    settings.AWS_ACCESS_KEY_ID = None
    
    print("\n--- 2. Testing Avatar Upload (PUT /v1/me/profile/avatar) ---")
    response = client.put(
        "/v1/me/profile/avatar",
        files={"file": ("avatar.png", dummy_png, "image/png")}
    )
    
    print(f"Status Code: {response.status_code}")
    response_json = response.json()
    print(f"Response: {response_json}")
    
    assert response.status_code == 200
    assert "media/images/" in response_json["data"]["profile_image_url"]
    
    local_path = response_json["data"]["profile_image_url"]
    print(f"[SUCCESS] Avatar fallback succeeded! Local Path: {local_path}")
    
    # Verify local file exists on disk
    local_file = Path(local_path)
    print(f"Local file exists on disk: {local_file.exists()}")
    assert local_file.exists()

    # Cleanup the test file
    if local_file.exists():
        local_file.unlink()
        print("Cleaned up dummy avatar image.")

finally:
    # Cleanup dependency overrides
    app.dependency_overrides.clear()
