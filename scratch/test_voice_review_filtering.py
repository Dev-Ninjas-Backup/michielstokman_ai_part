import sys
import os
import uuid

# Force stdout to use utf-8 to prevent emoji encoding errors on Windows terminals
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_admin_user
from app.model.user import User
from app.model.story import Story, StoryType, GenerationStatus

# Mock DB
mock_db = MagicMock()
app.dependency_overrides[get_db] = lambda: mock_db

# Override standard admin user auth
admin_user = User(id=uuid.uuid4(), email="admin@example.com", is_admin=True)
app.dependency_overrides[get_current_admin_user] = lambda: admin_user

def test_voice_review_filtering():
    client = TestClient(app)

    # Mock voice review stats:
    # 2 confessions (Stories), 1 meditation
    mock_stats = {
        "confession": 2,
        "meditation": 1
    }

    # Mock stories return list
    from datetime import datetime
    mock_confessions = [
        Story(
            id=uuid.uuid4(),
            title="A story about presence",
            story_type=StoryType.confession,
            voice_name="Aria (Warm)",
            audio_duration_seconds=272,
            audio_path="media/audio/1.mp3",
            created_at=datetime.now()
        ),
        Story(
            id=uuid.uuid4(),
            title="Letting go of fear",
            story_type=StoryType.confession,
            voice_name="Nova (Calm)",
            audio_duration_seconds=272,
            audio_path="media/audio/2.mp3",
            created_at=datetime.now()
        )
    ]
    mock_meditations = [
        Story(
            id=uuid.uuid4(),
            title="Breathing light meditation",
            story_type=StoryType.meditation,
            voice_name="Nova (Calm)",
            audio_duration_seconds=272,
            audio_path="media/audio/3.mp3",
            created_at=datetime.now()
        )
    ]

    with patch("app.data.voice_review.get_voice_review_stats") as mock_get_stats, \
         patch("app.data.voice_review.get_voice_review_stories") as mock_get_stories:
        
        mock_get_stats.return_value = mock_stats

        # 1. Test Fetching All
        mock_get_stories.return_value = (mock_confessions + mock_meditations, 3)
        print("Testing Voice Review GET /v1/admin/voice-review (All)...")
        r = client.get("/v1/admin/voice-review")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        assert data["data"]["all"] == 3
        assert data["data"]["stories"] == 2
        assert data["data"]["meditations"] == 1
        assert len(data["data"]["items"]) == 3

        # 2. Test Filtering by Story
        mock_get_stories.return_value = (mock_confessions, 2)
        print("Testing Voice Review GET /v1/admin/voice-review?story_type=story...")
        r = client.get("/v1/admin/voice-review", params={"story_type": "story"})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        assert data["data"]["all"] == 3  # stats remain total in DB
        assert data["data"]["stories"] == 2
        assert data["data"]["meditations"] == 1
        assert len(data["data"]["items"]) == 2
        assert all(item["story_type"] == "Story" for item in data["data"]["items"])

        # 3. Test Filtering by Meditation
        mock_get_stories.return_value = (mock_meditations, 1)
        print("Testing Voice Review GET /v1/admin/voice-review?story_type=meditation...")
        r = client.get("/v1/admin/voice-review", params={"story_type": "meditation"})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        assert data["data"]["all"] == 3
        assert data["data"]["stories"] == 2
        assert data["data"]["meditations"] == 1
        assert len(data["data"]["items"]) == 1
        assert all(item["story_type"] == "Meditations" for item in data["data"]["items"])

    print("[SUCCESS] All Voice Review filtering and tab counting tests passed perfectly!")

if __name__ == "__main__":
    test_voice_review_filtering()
