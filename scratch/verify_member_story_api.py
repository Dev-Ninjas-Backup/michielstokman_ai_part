"""
HTTP-level verification of the member story workspace using FastAPI TestClient.

The LLM is mocked so no provider keys are needed; ElevenLabs falls back to its
built-in mock TTS path when ELEVENLABS_API_KEY is absent.

    env PYTHONPATH=. DB_USER=... DB_PASSWORD=... DB_HOST=127.0.0.1 DB_PORT=55432 \
        DB_NAME=testdb .venv/bin/python scratch/verify_member_story_api.py
"""
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

failures = []


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


STORY_OUTPUT = (
    "TITLE: The Room I Never Left\n"
    "IMAGE_PROMPT: a warm collage cover with soft light\n"
    "STORY: I stayed in that room long after the door opened. "
    "The quiet was not peace, it was practice. I am still learning the difference."
)
INTRO_OUTPUT = (
    '{"instagram":"Some doors open long before we walk through them. Listen.",'
    '"facebook":"A confession about the quiet we mistake for peace, and the slow work of leaving it.",'
    '"spotify":"This is a confession about the rooms we stay in. It moves slowly, and it does not resolve."}'
)


def fake_llm(output):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=output)
    return llm


client = TestClient(app)
email = f"api-{uuid.uuid4().hex[:8]}@example.com"

# --- auth -----------------------------------------------------------------
r = client.post("/v1/signup", json={"email": email, "password": "secret123"})
check("signup succeeds", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
token = r.json().get("access_token") or r.json()["data"]["access_token"]
auth = {"Authorization": f"Bearer {token}"}

# --- voice catalog --------------------------------------------------------
r = client.get("/v1/voices", headers=auth)
check("GET /v1/voices returns 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
data = r.json()["data"]
check("catalog lists 5 selectable voices", len(data["voices"]) == 5, str(len(data["voices"])))
check("catalog has no custom voice yet", data["custom_voice"] is None)
check("catalog names are usable",
      {v["name"] for v in data["voices"]} == {"Sophia", "Charlotte", "Calen", "Victoria", "Anja"},
      str([v["name"] for v in data["voices"]]))

r = client.get("/v1/voices")
check("voices requires auth", r.status_code == 401, str(r.status_code))

# --- generate a story with an explicit voice ------------------------------
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)):
    r = client.post(
        "/v1/ai/story/generate",
        headers=auth,
        json={
            "story_type": "confession",
            "title": "The Room I Never Left",
            "first_name": "Mara",
            "story_input": "I stayed too long in a place that stopped being mine.",
            "tags": ["silence", "leaving"],
            "voice_name": "Charlotte",
        },
    )
check("story generation accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
payload = r.json()["data"]
story_id = payload["story_id"]
check("response carries story number", payload["story_number"] is not None, str(payload["story_number"]))
check("response carries reference", (payload["story_reference"] or "").startswith("TTL-"),
      str(payload["story_reference"]))

r = client.post("/v1/ai/story/generate", headers=auth,
                json={"story_type": "confession", "story_input": "x", "voice_name": "Bogus"})
check("unknown voice rejected at request time", r.status_code == 422, str(r.status_code))

r = client.post("/v1/ai/story/generate", headers=auth,
                json={"story_type": "confession", "story_input": "x", "use_custom_voice": True})
check("custom voice without upload rejected", r.status_code == 422, f"{r.status_code} {r.text[:120]}")

# --- library --------------------------------------------------------------
r = client.get("/v1/me/stories", headers=auth)
check("GET /v1/me/stories returns 200", r.status_code == 200, str(r.status_code))
listing = r.json()["data"]
check("library contains the story", listing["meta"]["total"] >= 1, str(listing["meta"]))
item = next(s for s in listing["stories"] if s["id"] == story_id)
check("story completed via background task", item["generation_status"] == "completed",
      item["generation_status"])
check("chosen voice was used", item["voice_name"] == "Charlotte", str(item["voice_name"]))

r = client.get(f"/v1/me/stories/{story_id}", headers=auth)
detail = r.json()["data"]
check("detail returns narrated text", "room" in (detail["story_text"] or "").lower(),
      (detail["story_text"] or "")[:60])
check("detail returns original input",
      detail["story_input"] == "I stayed too long in a place that stopped being mine.")
check("title survived generation", detail["title"] == "The Room I Never Left", str(detail["title"]))

# --- cross-user isolation -------------------------------------------------
other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
r = client.post("/v1/signup", json={"email": other_email, "password": "secret123"})
other_token = r.json().get("access_token") or r.json()["data"]["access_token"]
other_auth = {"Authorization": f"Bearer {other_token}"}

r = client.get(f"/v1/me/stories/{story_id}", headers=other_auth)
check("another member gets 404", r.status_code == 404, str(r.status_code))
r = client.post(f"/v1/me/stories/{story_id}/withdraw", headers=other_auth)
check("another member cannot withdraw", r.status_code == 404, str(r.status_code))
r = client.get("/v1/me/stories", headers=other_auth)
check("another member sees empty library", r.json()["data"]["meta"]["total"] == 0)

# --- withdraw / resubmit --------------------------------------------------
r = client.post(f"/v1/me/stories/{story_id}/withdraw", headers=auth)
check("withdraw returns 200", r.status_code == 200, f"{r.status_code} {r.text[:140]}")
check("withdraw reports status", r.json()["data"]["submission_status"] == "withdrawn")

r = client.get(f"/v1/stories/{story_id}", headers=auth)
check("withdrawn story hidden from public detail", r.status_code == 404, str(r.status_code))

r = client.post(f"/v1/me/stories/{story_id}/resubmit", headers=auth)
check("resubmit returns 200", r.status_code == 200, f"{r.status_code} {r.text[:140]}")
check("resubmit reports status", r.json()["data"]["submission_status"] == "submitted")

r = client.post(f"/v1/me/stories/{story_id}/resubmit", headers=auth)
check("resubmitting a live story is rejected", r.status_code == 409, str(r.status_code))

# --- re-narrate -----------------------------------------------------------
r = client.post(f"/v1/me/stories/{story_id}/narrate", headers=auth, json={"voice_name": "Calen"})
check("re-narrate accepted", r.status_code == 202, f"{r.status_code} {r.text[:160]}")
r = client.get(f"/v1/me/stories/{story_id}", headers=auth)
check("voice switched after re-narration", r.json()["data"]["voice_name"] == "Calen",
      str(r.json()["data"]["voice_name"]))
check("story text unchanged by re-narration",
      r.json()["data"]["story_input"] == "I stayed too long in a place that stopped being mine.")

r = client.post(f"/v1/me/stories/{story_id}/narrate", headers=auth, json={})
check("re-narrate needs a voice", r.status_code == 422, str(r.status_code))

# --- edit without regeneration -------------------------------------------
r = client.patch(f"/v1/me/stories/{story_id}", headers=auth,
                 json={"title": "Corrected Title", "regenerate": False})
check("metadata-only edit returns 200", r.status_code == 200, f"{r.status_code} {r.text[:140]}")
check("title updated", r.json()["data"]["title"] == "Corrected Title")
check("edit resets moderation", r.json()["data"]["moderation_status"] == "pending")

# --- edit with regeneration ----------------------------------------------
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)):
    r = client.patch(
        f"/v1/me/stories/{story_id}",
        headers=auth,
        json={"story_input": "I finally described the room out loud.", "voice_name": "Sophia"},
    )
check("regeneration accepted", r.status_code == 202, f"{r.status_code} {r.text[:200]}")
r = client.get(f"/v1/me/stories/{story_id}", headers=auth)
detail = r.json()["data"]
check("regeneration completed", detail["generation_status"] == "completed",
      detail["generation_status"])
check("regeneration counted", detail["regeneration_count"] == 1, str(detail["regeneration_count"]))
check("regeneration applied new voice", detail["voice_name"] == "Sophia", str(detail["voice_name"]))
check("regeneration used edited input",
      detail["story_input"] == "I finally described the room out loud.")

r = client.patch(f"/v1/me/stories/{story_id}", headers=auth, json={"story_input": "   "})
check("empty story input rejected", r.status_code == 422, str(r.status_code))

# --- social intros --------------------------------------------------------
with patch("app.services.service_member_story.get_story_llm", return_value=fake_llm(INTRO_OUTPUT)):
    r = client.post(f"/v1/me/stories/{story_id}/social-intros", headers=auth)
check("social intros generated", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
intros = r.json()["data"]["social_intros"]
check("instagram intro is a teaser", 0 < len(intros["instagram"]) <= 220, str(len(intros["instagram"])))
check("spotify intro is the longest", len(intros["spotify"]) > len(intros["instagram"]))

r = client.get(f"/v1/me/stories/{story_id}/share", headers=auth)
check("share package returns 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
pkg = r.json()["data"]
check("share package has all three intros",
      set(pkg["intros"].keys()) == {"instagram", "facebook", "spotify"}, str(pkg["intros"].keys()))
check("share package has audio", bool(pkg["audio_url"]), str(pkg["audio_url"]))
check("share package has a public link", story_id in (pkg["share_url"] or ""))
check("share package carries the story number", pkg["story_reference"].startswith("TTL-"))

# --- image upload ---------------------------------------------------------
png = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae426082"
)
r = client.post(f"/v1/me/stories/{story_id}/image", headers=auth,
                files={"image": ("cover.png", png, "image/png")})
check("image upload returns 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check("image marked as user uploaded", r.json()["data"]["image_source"] == "user_uploaded",
      str(r.json()["data"]["image_source"]))

r = client.post(f"/v1/me/stories/{story_id}/image", headers=auth,
                files={"image": ("bad.txt", b"nope", "text/plain")})
check("non-image upload rejected", r.status_code == 415, str(r.status_code))

# --- custom voice endpoints ----------------------------------------------
r = client.get("/v1/me/voice", headers=auth)
check("custom voice status reports none", r.json()["data"]["has_custom_voice"] is False)
r = client.post("/v1/me/voice", headers=auth,
                files={"recordings": ("clip.mp3", b"tiny", "audio/mpeg")})
check("too-short recording rejected", r.status_code == 422, f"{r.status_code} {r.text[:140]}")
r = client.post("/v1/me/voice", headers=auth,
                files={"recordings": ("clip.txt", b"x" * 40000, "text/plain")})
check("non-audio recording rejected", r.status_code == 415, str(r.status_code))

r = client.post("/v1/me/voice", headers=auth,
                files={"recordings": ("clip.mp3", b"\x00" * 40000, "audio/mpeg")})
check("valid recording accepted (mock clone)", r.status_code == 201, f"{r.status_code} {r.text[:160]}")
r = client.get("/v1/voices", headers=auth)
check("catalog now exposes custom voice", r.json()["data"]["custom_voice"] is not None)
r = client.post(f"/v1/me/stories/{story_id}/narrate", headers=auth, json={"use_custom_voice": True})
check("narrate with custom voice accepted", r.status_code == 202, f"{r.status_code} {r.text[:140]}")
r = client.get(f"/v1/me/stories/{story_id}", headers=auth)
check("story flagged as custom-voiced", r.json()["data"]["uses_custom_voice"] is True)
r = client.delete("/v1/me/voice", headers=auth)
check("custom voice deleted", r.status_code == 200 and
      r.json()["data"]["has_custom_voice"] is False)

# --- admin endpoints now require auth ------------------------------------
r = client.post("/v1/admin/ai/generate/bulk",
                json={"topic": "x", "story_type": "confession"})
check("bulk generation requires auth", r.status_code == 401, str(r.status_code))
r = client.post("/v1/admin/ai/generate/bulk", headers=auth,
                json={"topic": "x", "story_type": "confession"})
check("bulk generation requires admin", r.status_code == 403, str(r.status_code))
r = client.post("/v1/admin/ai/generate/submission", headers=auth,
                json={"submission_id": str(uuid.uuid4())})
check("submission generation requires admin", r.status_code == 403, str(r.status_code))

# --- job status scoping ---------------------------------------------------
# Use a freshly generated story: job_id is a single column, so the original
# generation's id was overwritten by the later re-narration and regeneration.
with patch("app.services.service_ai.get_story_llm", return_value=fake_llm(STORY_OUTPUT)):
    r = client.post("/v1/ai/story/generate", headers=auth,
                    json={"story_type": "meditation", "story_input": "Settling into the evening."})
fresh_job_id = r.json()["data"]["job_id"]

r = client.get(f"/v1/admin/ai/status/{fresh_job_id}")
check("job status requires auth", r.status_code == 401, str(r.status_code))
r = client.get(f"/v1/admin/ai/status/{fresh_job_id}", headers=other_auth)
check("job status hidden from other members", r.status_code == 404, str(r.status_code))
r = client.get(f"/v1/admin/ai/status/{fresh_job_id}", headers=auth)
check("owner can read own job status", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
check("job status exposes generated text", bool(r.json()["data"]["story_text"]))

# --- deletion -------------------------------------------------------------
r = client.delete(f"/v1/me/stories/{story_id}", headers=other_auth)
check("another member cannot delete", r.status_code == 404, str(r.status_code))
r = client.delete(f"/v1/me/stories/{story_id}", headers=auth)
check("owner can delete", r.status_code == 200, f"{r.status_code} {r.text[:140]}")
r = client.get(f"/v1/me/stories/{story_id}", headers=auth)
check("deleted story is gone", r.status_code == 404, str(r.status_code))

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("All API checks passed.")
