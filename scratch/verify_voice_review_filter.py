import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app

def test_voice_review_schema():
    client = TestClient(app)
    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]
    
    # Check that GET parameters description has "All, Stories, Meditations"
    get_params = paths["/v1/admin/voice-review"]["get"]["parameters"]
    story_type_param = next(p for p in get_params if p["name"] == "story_type")
    print(f"story_type param: {story_type_param}")
    
    assert "All" in story_type_param["schema"]["enum"]
    assert "Stories" in story_type_param["schema"]["enum"]
    assert "Meditations" in story_type_param["schema"]["enum"]
    print("Schema is correct and includes All, Stories, Meditations enum!")

if __name__ == "__main__":
    test_voice_review_schema()
