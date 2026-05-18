import sys
import os
import uuid

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set UTF-8 encoding for Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_admin_user
from app.model.user import User
from app.model.cover_image import CoverImage, CoverImageType

# Mock DB
mock_db = MagicMock()
app.dependency_overrides[get_db] = lambda: mock_db

# Override standard admin user auth
admin_user = User(id=uuid.uuid4(), email="admin@example.com", is_admin=True)
app.dependency_overrides[get_current_admin_user] = lambda: admin_user

def test_photos_journey():
    client = TestClient(app)

    # 1. Verify OpenAPI Schema accepts "journey" instead of "transformation"
    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]

    # Check that POST parameters description doesn't have "transformation" but "journey"
    schema_ref = paths["/v1/admin/photos"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    schema_name = schema_ref.split("/")[-1]
    properties = openapi["components"]["schemas"][schema_name]["properties"]
    post_params = properties["story_type"]
    print("Checking POST story_type description...")
    print(f"Description: {post_params.get('description')}")
    assert "journey" in post_params.get("description", "").lower()
    assert "transformation" not in post_params.get("description", "").lower()

    from datetime import datetime, timezone
    
    # 2. Mock GET List with journey type filter
    mock_cover = CoverImage(
        id=uuid.uuid4(),
        story_type=CoverImageType.transformation,
        image_url="https://s3.amazonaws.com/bucket/journey.jpg",
        s3_key="journey.jpg",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    with patch("app.data.cover_image.list_cover_images") as mock_list:
        mock_list.return_value = ([mock_cover], 1)
        
        print("Testing GET /v1/admin/photos?story_type=journey...")
        r = client.get("/v1/admin/photos", params={"story_type": "journey"})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        assert data["data"]["items"][0]["story_type"] == "Journey"
        
        # Verify it mapped journey -> transformation in db query call
        called_args, called_kwargs = mock_list.call_args
        assert called_kwargs["story_type"] == CoverImageType.transformation

    # 3. Mock POST cover image with journey type
    with patch("app.data.cover_image.create_cover_image") as mock_create, \
         patch("app.api.v1.endpoints.admin.route_photo_management.upload_image_to_s3") as mock_s3:
        mock_s3.return_value = ("https://s3.amazonaws.com/bucket/journey.jpg", "journey.jpg")
        mock_create.return_value = mock_cover
        
        print("Testing POST /v1/admin/photos with story_type=journey...")
        r = client.post(
            "/v1/admin/photos",
            data={"story_type": "journey"},
            files={"file": ("test.png", b"fakebytes", "image/png")}
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 201
        assert data["data"]["story_type"] == "Journey"
        
        # Verify it mapped journey -> transformation in database insertion
        called_args, called_kwargs = mock_create.call_args
        assert called_kwargs["story_type"] == CoverImageType.transformation

    print("All cover image 'journey' renaming tests passed successfully!")

if __name__ == "__main__":
    test_photos_journey()
