"""
Ad-hoc verification for the member story workspace.

Run against a throwaway Postgres:
    env DB_USER=... DB_PASSWORD=... DB_HOST=127.0.0.1 DB_PORT=55432 DB_NAME=testdb \
        .venv/bin/python scratch/verify_member_story_workspace.py
"""
import uuid

from app.core.db import SessionLocal
import app.data.story as story_data
import app.data.credit as credit_data
from app.model.credit import UserCredit
from app.model.profile import UserProfile
from app.model.story import ImageSource, StoryType, SubmissionStatus
from app.model.user import User
from app.schemas.schema_ai import StoryGenerateRequest
from app.services.service_ai import AIService
from app.services.service_member_story import (
    MemberStoryService,
    story_reference,
    to_detail,
)

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


db = SessionLocal()

# --- fixtures -------------------------------------------------------------
user = User(email=f"member-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", is_active=True)
other = User(email=f"other-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", is_active=True)
db.add_all([user, other])
db.commit()
db.refresh(user)
db.refresh(other)

profile = UserProfile(user_id=user.id, true_name="Mara", gender="female")
db.add(profile)
db.commit()

# --- story_number sequence ------------------------------------------------
s1 = story_data.create_story(db, StoryType.confession, str(uuid.uuid4()), user_id=str(user.id),
                             title="First", story_input="I kept quiet for years.")
s2 = story_data.create_story(db, StoryType.meditation, str(uuid.uuid4()), user_id=str(user.id),
                             title="Second", story_input="Breathing into the ache.")
s_other = story_data.create_story(db, StoryType.confession, str(uuid.uuid4()), user_id=str(other.id),
                                  title="Not mine", story_input="Someone else's story.")

check("story_number auto-allocated", s1.story_number is not None, f"got {s1.story_number}")
check("story_number increments", s2.story_number == s1.story_number + 1,
      f"{s1.story_number} -> {s2.story_number}")
check("story_reference formatted", story_reference(s1) == f"TTL-{s1.story_number:06d}",
      story_reference(s1))
check("defaults to submitted", s1.submission_status == SubmissionStatus.submitted)

# --- ownership scoping ----------------------------------------------------
check("owner can fetch own story",
      story_data.get_member_story(db, str(s1.id), str(user.id)) is not None)
check("cannot fetch another member's story",
      story_data.get_member_story(db, str(s_other.id), str(user.id)) is None)
check("malformed id returns None",
      story_data.get_member_story(db, "not-a-uuid", str(user.id)) is None)

# --- library listing ------------------------------------------------------
listing = MemberStoryService.list_stories(db, user, page=1, limit=10)
check("listing scoped to member", listing.meta.total == 2, f"total={listing.meta.total}")
check("counts include submitted", listing.counts["submitted"] == 2, str(listing.counts))
filtered = MemberStoryService.list_stories(db, user, story_type="meditation")
check("story_type filter works", filtered.meta.total == 1, f"total={filtered.meta.total}")

# --- withdraw / resubmit --------------------------------------------------
story_data.complete_story(db, s1, story_text="A finished confession.", title="First",
                          audio_path="media/audio/x.mp3")
MemberStoryService.withdraw(db, user, str(s1.id))
db.refresh(s1)
check("withdraw sets status", s1.submission_status == SubmissionStatus.withdrawn)
check("withdraw stamps time", s1.withdrawn_at is not None)

try:
    MemberStoryService.withdraw(db, user, str(s1.id))
    check("double withdraw rejected", False)
except Exception as exc:
    check("double withdraw rejected", getattr(exc, "status_code", None) == 409)

check("withdrawn hidden from moderation queue",
      all(str(row.id) != str(s1.id) for row in story_data.get_moderation_stories(db, limit=100)))

MemberStoryService.resubmit(db, user, str(s1.id))
db.refresh(s1)
check("resubmit restores status", s1.submission_status == SubmissionStatus.submitted)
check("resubmit clears withdrawn_at", s1.withdrawn_at is None)

# --- title preservation bug -----------------------------------------------
story_data.complete_story(db, s2, story_text="Body text.", title=None,
                          audio_path="media/audio/y.mp3")
db.refresh(s2)
check("title preserved when LLM omits TITLE", s2.title == "Second", f"got {s2.title!r}")

# --- credit refund --------------------------------------------------------
db.add(UserCredit(user_id=user.id, daily_credits_remaining=3, max_daily_credits=3))
db.commit()
credit_data.deduct_credit(db, str(user.id))
after_deduct = credit_data.get_or_create_credit(db, str(user.id)).daily_credits_remaining
credit_data.refund_credit(db, str(user.id))
after_refund = credit_data.get_or_create_credit(db, str(user.id)).daily_credits_remaining
check("refund restores credit", after_deduct == 2 and after_refund == 3,
      f"{after_deduct} -> {after_refund}")
credit_data.refund_credit(db, str(user.id))
check("refund capped at max",
      credit_data.get_or_create_credit(db, str(user.id)).daily_credits_remaining == 3)

# --- voice resolution -----------------------------------------------------
name, vid, custom = AIService.resolve_voice(gender="female", voice_name="calen")
check("explicit voice wins over gender", name == "Calen" and not custom, f"{name}/{custom}")
name, vid, custom = AIService.resolve_voice(gender="female", voice_name="Sophia",
                                            custom_voice_id="voice_abc")
check("cloned voice outranks catalog", custom and vid == "voice_abc", f"{name}/{vid}")
name, vid, custom = AIService.resolve_voice(gender="male", text="a plain english story")
check("auto-select returns real id", bool(vid) and not custom, f"{name}/{vid}")
name, vid, custom = AIService.resolve_voice(gender="female", voice_name="Nonexistent")
check("unknown name falls back to auto", bool(vid) and not custom, f"{name}")

try:
    StoryGenerateRequest(story_type="confession", story_input="x", voice_name="Bogus")
    check("schema rejects unknown voice", False)
except Exception:
    check("schema rejects unknown voice", True)
req = StoryGenerateRequest(story_type="confession", story_input="x", voice_name="sophia")
check("schema canonicalises voice case", req.voice_name == "Sophia", req.voice_name)

# --- custom voice guard ---------------------------------------------------
try:
    MemberStoryService._resolve_requested_voice(db, user, None, True)
    check("custom voice requires upload", False)
except Exception as exc:
    check("custom voice requires upload", getattr(exc, "status_code", None) == 422)

profile.custom_voice_id = "cloned_xyz"
profile.custom_voice_name = "Mara's Voice"
db.commit()
vname, cvid = MemberStoryService._resolve_requested_voice(db, user, None, True)
check("custom voice resolves once uploaded", cvid == "cloned_xyz", f"{vname}/{cvid}")
catalog = MemberStoryService.get_voice_catalog(db, user)
check("catalog exposes 5 voices", len(catalog.voices) == 5, str(len(catalog.voices)))
check("catalog exposes custom voice", catalog.custom_voice is not None)

# --- social intro parsing -------------------------------------------------
good = '{"instagram":"a","facebook":"b","spotify":"c"}'
fenced = '```json\n{"instagram":"a","facebook":"b","spotify":"c"}\n```'
noisy = 'Here you go:\n{"instagram":"a","facebook":"b","spotify":"c"}\nHope that helps!'
missing = '{"instagram":"a","facebook":"b"}'
check("parses plain json", MemberStoryService._parse_intro_json(good) is not None)
check("parses fenced json", MemberStoryService._parse_intro_json(fenced) is not None)
check("parses json with prose", MemberStoryService._parse_intro_json(noisy) is not None)
check("rejects incomplete json", MemberStoryService._parse_intro_json(missing) is None)
check("rejects garbage", MemberStoryService._parse_intro_json("no json at all") is None)

# --- cover provenance -----------------------------------------------------
story_data.set_story_cover(db, s1, "https://cdn/x.jpg", "images/x.jpg", ImageSource.user_uploaded)
db.refresh(s1)
check("cover source recorded", s1.image_source == ImageSource.user_uploaded)
check("cover key stored", s1.cover_image_key == "images/x.jpg")

# --- serializers ----------------------------------------------------------
detail = to_detail(s1)
check("detail carries reference", detail.story_reference == story_reference(s1))
check("detail exposes original input", detail.story_input == "I kept quiet for years.")
check("detail exposes narrated text", detail.story_text == "A finished confession.")

story_data.set_social_intros(db, s1, {"instagram": "a", "facebook": "b", "spotify": "c"})
db.refresh(s1)
check("has_social_intros flag set", to_detail(s1).has_social_intros is True)

pkg = MemberStoryService.get_share_package(db, user, str(s1.id))
check("share package returns intros", pkg.intros.spotify == "c")
check("share package has artwork", pkg.cover_image_url == "https://cdn/x.jpg")
check("share package has link", pkg.share_url.endswith(str(s1.id)))

db.close()

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    raise SystemExit(1)
print("All checks passed.")
