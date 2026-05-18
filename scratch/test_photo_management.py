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
from app.model.cover_image import CoverImage, CoverImageType
from app.api.deps import get_current_admin_user

client = TestClient(app)

# Create a mock admin user for bypass or inject via dependency override
db_gen = get_db()
db = next(db_gen)

# Find a real active user in the DB to test authentically
admin_user = db.query(User).first()

print(f"Using test admin user: {admin_user.email if admin_user else 'None'}")

# Override dependencies to make testing easier without JWT logins
if admin_user:
    app.dependency_overrides[get_current_admin_user] = lambda: admin_user

try:
    print("\n--- 1. Creating 1x1 Pixel Dummy Image ---")
    # 1x1 transparent pixel PNG bytes
    dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    
    # Temporarily unset S3 settings in memory to force fallback
    original_s3_key = settings.AWS_ACCESS_KEY_ID
    settings.AWS_ACCESS_KEY_ID = None
    
    print("\n--- 2. Testing Photo Upload (POST /v1/admin/photos) ---")
    response = client.post(
        "/v1/admin/photos",
        data={"story_type": "confession"},
        files={"file": ("test.png", dummy_png, "image/png")}
    )
    
    print(f"Status Code: {response.status_code}")
    response_json = response.json()
    print(f"Response: {response_json}")
    
    assert response.status_code == 200
    assert "media/images/" in response_json["data"]["image_url"]
    
    cover_id = response_json["data"]["id"]
    local_path = response_json["data"]["image_url"]
    print(f"[SUCCESS] Upload fallback succeeded! Cover Image ID: {cover_id}, Local Path: {local_path}")
    
    # Verify local file exists on disk
    local_file = Path(local_path)
    print(f"Local file exists on disk: {local_file.exists()}")
    assert local_file.exists()

    print("\n--- 3. Testing List Photos (GET /v1/admin/photos) ---")
    response = client.get("/v1/admin/photos", params={"story_type": "confession"})
    print(f"Status Code: {response.status_code}")
    print(f"Response Items count: {len(response.json()['data']['items'])}")
    assert response.status_code == 200

    print("\n--- 4. Testing Photo Detail (GET /v1/admin/photos/{id}) ---")
    response = client.get(f"/v1/admin/photos/{cover_id}")
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200
    
    print("\n--- 5. Testing Photo Deletion (DELETE /v1/admin/photos/{id}) ---")
    response = client.delete(f"/v1/admin/photos/{cover_id}")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    
    # Verify file was deleted from disk
    print(f"Local file exists on disk after deletion: {local_file.exists()}")
    assert not local_file.exists()
    print("[SUCCESS] Local deletion clean and complete!")

finally:
    # Cleanup dependency overrides
    app.dependency_overrides.clear()
