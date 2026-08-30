"""
HTTP-level verification of the admin moderation AI desk.

    env PYTHONPATH=. .venv/bin/python scratch/verify_admin_moderation_desk.py

Source-only blast-radius checks always run. The HTTP suite needs a configured DB.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


route_src = (ROOT / "app/api/v1/endpoints/admin/route_moderation.py").read_text()
schema_src = (ROOT / "app/schemas/schema_story.py").read_text()
public_schema = schema_src.split("User-facing")[-1]
member_schema = (ROOT / "app/schemas/schema_member_story.py").read_text()
story_data = (ROOT / "app/data/story.py").read_text()
ai_src = (ROOT / "app/services/service_ai.py").read_text()

update_fn = story_data.split("def update_story_details")[1].split("def delete_story")[0]
check("suggest endpoint exists", "/suggest" in route_src)
check("request-changes endpoint exists", "/request-changes" in route_src)
check("PUT still exists", '@router.put("/admin/moderation/story/{story_id}"' in route_src)
check("approve still exists", "/approve" in route_src)
check("public detail schema has no editorial_brief", "editorial_brief" not in public_schema)
check("member story schema has no editorial_brief", "editorial_brief" not in member_schema)
check("update_story_details never assigns audio_path", "story.audio_path" not in update_fn)
check("human_ready voice suggest is 409", "HTTP_409_CONFLICT" in route_src)
check("AI moods helper exists", "def generate_moods" in ai_src)
prompts_src = (ROOT / "app/utils/prompts.py").read_text()
moods_system = prompts_src.split("EDITORIAL_MOODS_SYSTEM")[1].split("EDITORIAL_MOODS_HUMAN")[0]
check(
    "moods system prompt escapes JSON braces for LangChain",
    '{{"tags"' in moods_system,
)
check("AI editorial brief helper exists", "def generate_editorial_brief" in ai_src)

print("")
print("--- HTTP suite ---")

try:
    from fastapi.testclient import TestClient

    from app.core.db import SessionLocal
    from app.main import app
    from app.model.story import Story, SubmissionMode
    from app.model.user import User
except ImportError as exc:
    print(f"SKIP HTTP suite ({exc}). Run from the API venv with DB configured:")
    print("  env PYTHONPATH=. .venv/bin/python scratch/verify_admin_moderation_desk.py")
    if failures:
        print(f"{len(failures)} failed: {failures}")
        raise SystemExit(1)
    raise SystemExit(0)


STORY_OUTPUT = (
    "TITLE: The Room I Never Left\n"
    "IMAGE_PROMPT: a warm collage cover with soft light\n"
    "STORY: I stayed in that room long after the door opened. "
    "The quiet was not peace, it was practice. I am still learning the difference."
)
HOOK_OUTPUT = "I stayed in that room long after the door opened. The quiet was not peace."
TAGLINE_OUTPUT = "A ROOM THAT KEPT\nTHE **QUIET** TOO LONG."
MOODS_OUTPUT = (
    '{"tags": ["silence", "leaving", "rooms"], '
    '"growth_areas": ["honesty"], "life_phase": "Leaving"}'
)
BRIEF_OUTPUT = "Intimate first-person tone. Watch for identifiable place names before publish."


def fake_llm(output):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=output)
    return llm


def promote_admin(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.is_admin = True
        db.commit()
    finally:
        db.close()


def set_human_ready(story_id: str) -> str:
    db = SessionLocal()
    try:
        row = db.query(Story).filter(Story.id == uuid.UUID(story_id)).one()
        row.submission_mode = SubmissionMode.human_ready
        if not row.audio_path:
            row.audio_path = "media/audio/uploaded-narration.mp3"
        audio = row.audio_path
        db.commit()
        return audio
    finally:
        db.close()


def read_audio(story_id: str) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(Story).filter(Story.id == uuid.UUID(story_id)).one()
        return row.audio_path
    finally:
        db.close()


client = TestClient(app)

member_email = f"mod-member-{uuid.uuid4().hex[:8]}@example.com"
admin_email = f"mod-admin-{uuid.uuid4().hex[:8]}@example.com"

r = client.post("/v1/signup", json={"email": member_email, "password": "secret123"})
check("member signup succeeds", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
member_token = r.json().get("access_token") or r.json()["data"]["access_token"]
member_auth = {"Authorization": f"Bearer {member_token}"}

r = client.post("/v1/signup", json={"email": admin_email, "password": "secret123"})
check("admin signup succeeds", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
admin_token = r.json().get("access_token") or r.json()["data"]["access_token"]
admin_auth = {"Authorization": f"Bearer {admin_token}"}
promote_admin(admin_email)

with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)):
    r = client.post(
        "/v1/ai/story/generate",
        headers=member_auth,
        json={
            "story_type": "confession",
            "title": "The Room I Never Left",
            "first_name": "Mara",
            "location": "Lisbon",
            "story_input": "I stayed too long in a place that stopped being mine.",
            "tags": ["silence"],
            "voice_name": "Charlotte",
        },
    )
check("story generation accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
story_id = r.json()["data"]["story_id"]

r = client.get("/v1/admin/moderation/queue", headers=member_auth)
check("member cannot open queue", r.status_code == 403, str(r.status_code))

r = client.get(f"/v1/admin/moderation/story/{story_id}", headers=admin_auth)
check("admin GET detail 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
detail = r.json()["data"]
hook_before = detail.get("hero_hook")
check("detail includes identity", detail.get("first_name") == "Mara", str(detail.get("first_name")))
check("detail includes voice_name", bool(detail.get("voice_name")), str(detail.get("voice_name")))
check("editorial_brief present as field", "editorial_brief" in detail)

r = client.post(
    f"/v1/admin/moderation/story/{story_id}/suggest",
    headers=member_auth,
    json={"field": "hook"},
)
check("member cannot suggest", r.status_code == 403, str(r.status_code))

with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(HOOK_OUTPUT)):
    r = client.post(
        f"/v1/admin/moderation/story/{story_id}/suggest",
        headers=admin_auth,
        json={"field": "hook"},
    )
check("suggest hook 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check("suggest returns hook", r.json()["data"]["hero_hook"] == HOOK_OUTPUT, str(r.json()["data"]))

r = client.get(f"/v1/admin/moderation/story/{story_id}", headers=admin_auth)
check(
    "suggest does not persist hook",
    r.json()["data"].get("hero_hook") == hook_before,
    str(r.json()["data"].get("hero_hook")),
)

with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(TAGLINE_OUTPUT)):
    r = client.post(
        f"/v1/admin/moderation/story/{story_id}/suggest",
        headers=admin_auth,
        json={"field": "tagline"},
    )
check("suggest tagline 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(MOODS_OUTPUT)):
    r = client.post(
        f"/v1/admin/moderation/story/{story_id}/suggest",
        headers=admin_auth,
        json={"field": "moods"},
    )
check("suggest moods 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
moods = r.json()["data"]
check("moods include tags", "silence" in (moods.get("tags") or []), str(moods.get("tags")))

with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(BRIEF_OUTPUT)):
    r = client.post(
        f"/v1/admin/moderation/story/{story_id}/suggest",
        headers=admin_auth,
        json={"field": "analysis"},
    )
check("suggest analysis 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check("analysis is private brief", BRIEF_OUTPUT in (r.json()["data"].get("editorial_brief") or ""))

r = client.put(
    f"/v1/admin/moderation/story/{story_id}",
    headers=admin_auth,
    json={
        "hero_hook": "Edited hook for the public page.",
        "hero_tagline": "A LINE THAT **STAYS**.",
        "first_name": "Mara",
        "location": "Porto",
        "tags": ["silence", "leaving"],
        "growth_areas": ["honesty"],
        "life_phase": "Leaving",
        "editorial_brief": "Admin kept this private.",
    },
)
check("expanded PUT 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
saved = r.json()["data"]
check("PUT saved hook", saved.get("hero_hook") == "Edited hook for the public page.")
check("PUT saved location", saved.get("location") == "Porto")
check("PUT saved editorial_brief", saved.get("editorial_brief") == "Admin kept this private.")

r = client.get(f"/v1/me/stories/{story_id}", headers=member_auth)
check("member detail still works after admin PUT", r.status_code == 200, str(r.status_code))
check(
    "member detail has no editorial_brief",
    "editorial_brief" not in r.json()["data"],
    str(list(r.json()["data"].keys())[:12]),
)

r = client.get(f"/v1/stories/{story_id}", headers=member_auth)
check("pending story hidden from public detail", r.status_code == 404, str(r.status_code))

r = client.post(
    f"/v1/admin/moderation/story/{story_id}/request-changes",
    headers=admin_auth,
    json={"reason": "Please shorten the opening."},
)
check("request-changes 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check("request-changes stays pending", r.json()["data"]["status"] == "pending")

r = client.get(f"/v1/me/stories/{story_id}", headers=member_auth)
check(
    "member sees request-changes note",
    r.json()["data"].get("moderation_notes") == "Please shorten the opening.",
    str(r.json()["data"].get("moderation_notes")),
)
check("member status still pending", r.json()["data"].get("moderation_status") == "pending")

r = client.get(f"/v1/stories/{story_id}", headers=member_auth)
check("request-changes still hidden from public", r.status_code == 404, str(r.status_code))

r = client.post(f"/v1/admin/moderation/story/{story_id}/approve", headers=admin_auth)
check("approve with empty body 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check("approve status approved", r.json()["data"]["status"] == "approved")

r = client.get(f"/v1/stories/{story_id}", headers=member_auth)
check("approved story is public", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
public = r.json()["data"]
check("public hero_hook is admin edit", public.get("hero_hook") == "Edited hook for the public page.")
check("public hero_tagline is admin edit", public.get("hero_tagline") == "A LINE THAT **STAYS**.")
check("public has no editorial_brief", "editorial_brief" not in public)

r = client.put(
    f"/v1/admin/moderation/story/{story_id}",
    headers=admin_auth,
    json={"title": "Title only"},
)
check("old PUT title-only still 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
check("title-only keeps hook", r.json()["data"].get("hero_hook") == "Edited hook for the public page.")

r = client.post(
    f"/v1/admin/moderation/story/{story_id}/reject",
    headers=admin_auth,
    json={"reason": "Not a fit for the catalog."},
)
check("reject still 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

# --- human-ready lock -----------------------------------------------------
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)):
    r = client.post(
        "/v1/ai/story/generate",
        headers=member_auth,
        json={
            "story_type": "confession",
            "title": "Kept Recording",
            "first_name": "Mara",
            "story_input": "This narration must not be replaced.",
            "voice_name": "Sophia",
        },
    )
check("second story generated", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
human_id = r.json()["data"]["story_id"]
audio_before = set_human_ready(human_id)

r = client.put(
    f"/v1/admin/moderation/story/{human_id}",
    headers=admin_auth,
    json={"story_text": "Slightly edited published text.", "voice_name": "Calen"},
)
check("human-ready PUT text 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check(
    "human-ready PUT ignores voice_name",
    r.json()["data"].get("voice_name") != "Calen",
    str(r.json()["data"].get("voice_name")),
)
check("human-ready audio_path unchanged", read_audio(human_id) == audio_before, read_audio(human_id))

r = client.post(
    f"/v1/admin/moderation/story/{human_id}/suggest",
    headers=admin_auth,
    json={"field": "voice"},
)
check("human-ready suggest voice 409", r.status_code == 409, f"{r.status_code} {r.text[:200]}")

r = client.post(
    f"/v1/admin/moderation/story/{human_id}/suggest",
    headers=admin_auth,
    json={"field": "not-a-field"},
)
check("invalid suggest field 422", r.status_code == 422, f"{r.status_code} {r.text[:160]}")

with patch("app.services.service_ai.get_story_llm", return_value=fake_llm("not json at all")):
    r = client.post(
        f"/v1/admin/moderation/story/{story_id}/suggest",
        headers=admin_auth,
        json={"field": "moods"},
    )
check("empty moods suggest is 502", r.status_code == 502, f"{r.status_code} {r.text[:200]}")

r = client.post(
    f"/v1/admin/moderation/story/{human_id}/request-changes",
    headers=admin_auth,
    json={"reason": "   "},
)
check("empty request-changes rejected", r.status_code == 422, str(r.status_code))

print("")
if failures:
    print(f"{len(failures)} failed: {failures}")
    raise SystemExit(1)
print("All admin moderation desk checks passed.")
