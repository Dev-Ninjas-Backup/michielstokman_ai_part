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

# Mock DB
mock_db = MagicMock()
app.dependency_overrides[get_db] = lambda: mock_db

# Override standard admin user auth
admin_user = User(id=uuid.uuid4(), email="admin@example.com", is_admin=True)
app.dependency_overrides[get_current_admin_user] = lambda: admin_user

def test_pagination_endpoints():
    client = TestClient(app)

    # 1. Verify Order History Pagination
    with patch("app.data.billing.list_admin_orders") as mock_list:
        mock_list.return_value = ([], 123)  # Empty list with 123 total items
        
        print("Testing GET /v1/admin/orders?limit=10&page=3...")
        r = client.get("/v1/admin/orders", params={"limit": 10, "page": 3})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        meta = data["data"]["meta"]
        assert meta["total"] == 123
        assert meta["page"] == 3
        assert meta["limit"] == 10
        assert meta["totalPages"] == 13

    # 2. Verify Voice Review Pagination
    with patch("app.data.voice_review.get_voice_review_stories") as mock_voice:
        mock_voice.return_value = ([], 45)
        
        print("Testing GET /v1/admin/voice-review?limit=10&page=2...")
        r = client.get("/v1/admin/voice-review", params={"limit": 10, "page": 2})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        meta = data["data"]["meta"]
        assert meta["total"] == 45
        assert meta["page"] == 2
        assert meta["limit"] == 10
        assert meta["totalPages"] == 5

    # 3. Verify Journey Management Pagination
    with patch("app.data.liberation_catalog.list_all_definitions") as mock_lib_list, \
         patch("app.data.liberation_catalog.count_all_definitions") as mock_lib_count:
        mock_lib_list.return_value = []
        mock_lib_count.return_value = 88
        
        print("Testing GET /v1/admin/liberation?limit=25&page=4...")
        r = client.get("/v1/admin/liberation", params={"limit": 25, "page": 4})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        meta = data["data"]["meta"]
        assert meta["total"] == 88
        assert meta["page"] == 4
        assert meta["limit"] == 25
        assert meta["totalPages"] == 4

    # 4. Verify Moderation Queue Pagination
    with patch("app.data.story.get_moderation_stories") as mock_mod_list, \
         patch("app.data.story.get_moderation_stats") as mock_mod_stats, \
         patch("app.data.story.count_moderation_stories") as mock_mod_count:
        mock_mod_list.return_value = []
        mock_mod_stats.return_value = {"pending": 2, "approved": 1}
        mock_mod_count.return_value = 3
        
        print("Testing GET /v1/admin/moderation/queue?limit=2&page=2...")
        r = client.get("/v1/admin/moderation/queue", params={"limit": 2, "page": 2})
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {data}\n")
        assert r.status_code == 200
        meta = data["data"]["meta"]
        assert meta["total"] == 3
        assert meta["page"] == 2
        assert meta["limit"] == 2
        assert meta["totalPages"] == 2

    print("All dashboard pagination tests passed successfully!")

if __name__ == "__main__":
    test_pagination_endpoints()
