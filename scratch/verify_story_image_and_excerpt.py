"""
Verifies the two additions to the member story workspace:

  1. `image_mode` on POST /v1/ai/story/generate — the member can opt out of AI
     artwork and attach their own image instead.
  2. `excerpt` on the member's own story list, matching what the discovery feed
     renders.

The LLM and the image generator are mocked, so no provider keys are needed.

    env PYTHONPATH=. DB_USER=testuser DB_PASSWORD=testpass DB_HOST=127.0.0.1 \
        DB_PORT=55432 DB_NAME=testdb .venv/bin/python scratch/verify_story_image_and_excerpt.py
"""
import io
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.utils.text import build_excerpt

failures = []


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


LONG_BODY = (
    "I stayed in that room long after the door opened.\n\n"
    "The quiet was not peace, it was practice, and I had been practising for years "
    "without noticing that the walls had started to lean inward toward me."
)
STORY_OUTPUT = (
    "TITLE: The Room I Never Left\n"
    "IMAGE_PROMPT: a warm collage cover with soft light\n"
    f"STORY: {LONG_BODY}"
)


def fake_llm(output):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=output)
    return llm


# ---------------------------------------------------------------------------
# 1. The excerpt helper itself
# ---------------------------------------------------------------------------

check("empty text yields no excerpt", build_excerpt("") is None)
check("None yields no excerpt", build_excerpt(None) is None)
check("whitespace-only yields no excerpt", build_excerpt("   \n\n  ") is None)

short = build_excerpt("A short confession.")
check("short text is returned whole", short == "A short confession.", repr(short))
check("short text gets no ellipsis", not short.endswith("…"), repr(short))

flat = build_excerpt("Line one.\n\nLine two.\tLine three.")
check("line breaks collapse to spaces", flat == "Line one. Line two. Line three.", repr(flat))

ssml = build_excerpt('She paused. <break time="2.0s" /> Then she spoke.')
check("ssml pause markers are stripped", "break" not in ssml, repr(ssml))

long_excerpt = build_excerpt(LONG_BODY)
check("long text is truncated", len(long_excerpt) <= 121, str(len(long_excerpt)))
check("truncated text ends with ellipsis", long_excerpt.endswith("…"), repr(long_excerpt))
check("truncation lands on a word boundary",
      long_excerpt.rstrip("…").split()[-1] in LONG_BODY.split(),
      repr(long_excerpt))
check("no dangling punctuation before ellipsis",
      not long_excerpt.rstrip("…").endswith((",", " ", ";")), repr(long_excerpt))

nospace = build_excerpt("x" * 400)
check("text without spaces still truncates", len(nospace) <= 121, str(len(nospace)))

# ---------------------------------------------------------------------------
# 2. API behaviour
# ---------------------------------------------------------------------------

client = TestClient(app)
email = f"img-{uuid.uuid4().hex[:8]}@example.com"

r = client.post("/v1/signup", json={"email": email, "password": "secret123"})
check("signup succeeds", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
token = r.json().get("access_token") or r.json()["data"]["access_token"]
auth = {"Authorization": f"Bearer {token}"}

base_payload = {
    "story_type": "confession",
    "title": "The Room I Never Left",
    "first_name": "Mara",
    "story_input": "I stayed too long in a place that stopped being mine.",
}

# --- default mode still asks for AI artwork --------------------------------
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)), \
     patch("app.utils.image_generator.generate_ai_cover_image",
           return_value=("https://cdn.example.com/ai-cover.jpg", "images/ai-cover.jpg")) as ai_cover, \
     patch("app.core.config.settings.OPENAI_API_KEY", "test-key"):
    r = client.post("/v1/ai/story/generate", headers=auth, json=dict(base_payload))
check("default generation accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
ai_story_id = r.json()["data"]["story_id"]
check("default image_mode echoed back", r.json()["data"]["image_mode"] == "ai_generated",
      str(r.json()["data"]["image_mode"]))
check("AI cover generator was called in default mode", ai_cover.call_count == 1,
      str(ai_cover.call_count))

r = client.get(f"/v1/me/stories/{ai_story_id}", headers=auth)
detail = r.json()["data"]
check("default mode records ai_generated provenance", detail["image_source"] == "ai_generated",
      str(detail["image_source"]))
check("default mode stores the generated cover",
      detail["cover_image_url"] == "https://cdn.example.com/ai-cover.jpg",
      str(detail["cover_image_url"]))

# --- user_uploaded mode skips the AI image call ----------------------------
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)), \
     patch("app.utils.image_generator.generate_ai_cover_image",
           return_value=("https://cdn.example.com/ai-cover.jpg", "images/ai-cover.jpg")) as ai_cover, \
     patch("app.core.config.settings.OPENAI_API_KEY", "test-key"):
    r = client.post("/v1/ai/story/generate", headers=auth,
                    json=dict(base_payload, image_mode="user_uploaded"))
check("user_uploaded generation accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
own_payload = r.json()["data"]
own_story_id = own_payload["story_id"]
check("user_uploaded image_mode echoed back", own_payload["image_mode"] == "user_uploaded",
      str(own_payload["image_mode"]))
check("AI cover generator was NOT called", ai_cover.call_count == 0, str(ai_cover.call_count))
check("message points at the upload endpoint",
      f"/v1/me/stories/{own_story_id}/image" in own_payload["message"],
      own_payload["message"][:160])

r = client.get(f"/v1/me/stories/{own_story_id}", headers=auth)
detail = r.json()["data"]
check("story still completed without AI art", detail["generation_status"] == "completed",
      str(detail["generation_status"]))
check("no AI artwork was attached", detail["image_source"] != "ai_generated",
      str(detail["image_source"]))

# --- the member attaches their own image -----------------------------------
png = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
with patch("app.utils.s3.upload_image_to_s3",
           return_value=("https://cdn.example.com/mine.png", "images/mine.png")):
    r = client.post(
        f"/v1/me/stories/{own_story_id}/image",
        headers=auth,
        files={"image": ("mine.png", io.BytesIO(png), "image/png")},
    )
check("own image upload accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
uploaded = r.json()["data"]
check("upload records user_uploaded provenance", uploaded["image_source"] == "user_uploaded",
      str(uploaded["image_source"]))
check("upload returns the member's image",
      uploaded["cover_image_url"] == "https://cdn.example.com/mine.png",
      str(uploaded["cover_image_url"]))

r = client.post(f"/v1/me/stories/{own_story_id}/image", headers=auth,
                files={"image": ("bad.txt", io.BytesIO(b"nope"), "text/plain")})
check("non-image upload rejected", r.status_code == 415, str(r.status_code))

r = client.post("/v1/ai/story/generate", headers=auth,
                json=dict(base_payload, image_mode="something_else"))
check("unknown image_mode rejected", r.status_code == 422, str(r.status_code))

# --- a member-uploaded cover survives regeneration -------------------------
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)), \
     patch("app.utils.image_generator.generate_ai_cover_image",
           return_value=("https://cdn.example.com/ai-cover.jpg", "images/ai-cover.jpg")) as ai_cover, \
     patch("app.core.config.settings.OPENAI_API_KEY", "test-key"):
    r = client.patch(f"/v1/me/stories/{own_story_id}", headers=auth,
                     json={"story_input": "I finally described the room out loud.",
                           "regenerate": True})
check("regeneration accepted", r.status_code == 202, f"{r.status_code} {r.text[:200]}")
check("regeneration left the member's cover alone", ai_cover.call_count == 0, str(ai_cover.call_count))

r = client.get(f"/v1/me/stories/{own_story_id}", headers=auth)
detail = r.json()["data"]
check("member cover survives regeneration",
      detail["cover_image_url"] == "https://cdn.example.com/mine.png",
      str(detail["cover_image_url"]))

# ---------------------------------------------------------------------------
# 3. Excerpt on the member's own library
# ---------------------------------------------------------------------------

r = client.get("/v1/me/stories", headers=auth)
check("library returns 200", r.status_code == 200, str(r.status_code))
listing = r.json()["data"]
item = next(s for s in listing["stories"] if s["id"] == ai_story_id)

check("list item exposes an excerpt", item.get("excerpt"), str(item.get("excerpt"))[:80])
check("excerpt is short enough for a card", len(item["excerpt"]) <= 121, str(len(item["excerpt"])))
check("excerpt has no raw line breaks", "\n" not in item["excerpt"])
check("list item still omits the full text", "story_text" not in item, str(list(item.keys())))

r = client.get(f"/v1/me/stories/{ai_story_id}", headers=auth)
detail = r.json()["data"]
check("detail still returns the full text",
      len(detail["story_text"]) > len(item["excerpt"]), str(len(detail["story_text"])))
check("excerpt is a prefix of the full story",
      detail["story_text"].replace("\n", " ").startswith(item["excerpt"].rstrip("…")[:40]),
      item["excerpt"][:60])

# A story still generating has no text yet, so no excerpt.
with patch("app.services.service_ai.get_story_llm", side_effect=RuntimeError("provider down")):
    r = client.post("/v1/ai/story/generate", headers=auth, json=dict(base_payload))
failed_id = r.json()["data"]["story_id"]
r = client.get(f"/v1/me/stories/{failed_id}", headers=auth)
check("story with no text has a null excerpt", r.json()["data"]["excerpt"] is None,
      str(r.json()["data"]["excerpt"]))

# ---------------------------------------------------------------------------
# 4. Discovery feed uses the same excerpt
# ---------------------------------------------------------------------------

from app.core.db import SessionLocal
from app.model.story import ModerationStatus, Story

db = SessionLocal()
row = db.query(Story).filter(Story.id == uuid.UUID(ai_story_id)).first()
row.moderation_status = ModerationStatus.approved
db.commit()
db.close()

r = client.get("/v1/dashboard/feed")
check("feed returns 200", r.status_code == 200, str(r.status_code))
feed_item = next(i for i in r.json()["data"]["items"] if i.get("id") == ai_story_id)
check("feed exposes excerpt", feed_item.get("excerpt"), str(feed_item.get("excerpt"))[:80])
check("feed excerpt matches the library excerpt", feed_item["excerpt"] == item["excerpt"],
      f"{feed_item.get('excerpt')!r} vs {item['excerpt']!r}")
check("legacy description field still populated",
      feed_item.get("description") == feed_item.get("excerpt"),
      str(feed_item.get("description"))[:60])

# ---------------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    raise SystemExit(1)
print("All checks passed.")
