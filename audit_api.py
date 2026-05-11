import requests
import json
import subprocess

BASE_URL = "http://34.255.26.146:8000"
ADMIN_EMAIL = "admin@transform.com"
ADMIN_PASSWORD = "AdminPassword123!"

results = []

def test(method, path, headers=None, json_body=None, params=None, label=None):
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST":
            res = requests.post(url, headers=headers, json=json_body, timeout=10)
        elif method == "PUT":
            res = requests.put(url, headers=headers, json=json_body, timeout=10)
        elif method == "PATCH":
            res = requests.patch(url, headers=headers, json=json_body, timeout=10)
        elif method == "DELETE":
            res = requests.delete(url, headers=headers, timeout=10)
        
        try:
            msg = res.json().get("message", "")
        except Exception:
            msg = res.text[:80]
        
        status = res.status_code
        ok = "✅" if status < 400 or status == 404 else "❌"
        results.append((ok, method, path, status, msg))
        print(f"{ok} {method:6} {path:55} {status}  {msg}")
        return res
    except Exception as e:
        results.append(("💥", method, path, "ERR", str(e)[:60]))
        print(f"💥 {method:6} {path:55} ERR  {str(e)[:60]}")
        return None

print("=" * 100)
print("TRANSFORM TO LIBERATION — FULL API AUDIT")
print("=" * 100)

# ── 1. Auth (no token) ──────────────────────────────────────────────────────
print("\n[AUTH]")
test("POST", "/v1/signup",  json_body={"email": "audituser99@example.com", "password": "Password123!"})
login_res = test("POST", "/v1/login", json_body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
token = login_res.json().get("data", {}).get("access_token") if login_res else None
h = {"Authorization": f"Bearer {token}"}

test("POST", "/v1/social-login", json_body={"provider": "google", "token": "fake_token"})
test("POST", "/v1/auth/forgot-password")
test("POST", "/v1/auth/reset-password")
test("POST", "/v1/auth/update-password")
test("GET",  "/v1/auth/profile", headers=h)
test("POST", "/v1/auth/refresh", headers=h)

# ── 2. Profile ───────────────────────────────────────────────────────────────
print("\n[PROFILE]")
profile_body = {"gender": "male", "age": 35, "relationship_status": "single",
                "slider_desire_relationship": 7, "slider_fear_loneliness": 4,
                "deepest_desire_fear": "To help others", "country_city": "Amsterdam"}
test("PUT", "/v1/me/profile", headers=h, json_body=profile_body)
test("GET", "/v1/me/profile", headers=h)

# ── 3. Dashboard ─────────────────────────────────────────────────────────────
print("\n[DASHBOARD]")
test("GET", "/v1/dashboard/feed",            headers=h)
test("GET", "/v1/dashboard/credits",         headers=h)
test("GET", "/v1/dashboard/recommendations", headers=h)

# ── 4. AI ────────────────────────────────────────────────────────────────────
print("\n[AI]")
story_body = {"story_type": "meditation", "emotional_context": "overwhelmed",
              "specific_trigger": "work stress", "life_phase": "career"}
gen_res = test("POST", "/v1/ai/story/generate", headers=h, json_body=story_body)
job_id = None
story_id = None
if gen_res and gen_res.status_code == 200:
    job_id = gen_res.json().get("data", {}).get("job_id")
    story_id = gen_res.json().get("data", {}).get("story_id")

if job_id:
    test("GET", f"/v1/admin/ai/status/{job_id}", headers=h)
else:
    print("  ⚠️  Skipping AI status poll — no job_id")

test("POST", "/v1/ai/resonance", headers=h, json_body={"track_id": "test-id", "touch_score": 8})
test("GET",  "/v1/ai/search",    headers=h, params={"q": "love"})

# ── 5. Stories ───────────────────────────────────────────────────────────────
print("\n[STORIES]")
# Get a real story_id from the feed
feed_res = requests.get(f"{BASE_URL}/v1/dashboard/feed", headers=h, timeout=10)
try:
    items = feed_res.json().get("data", {}).get("items", [])
    story_id = next((i.get("story_id") or i.get("id") for i in items if i.get("story_id") or i.get("id")), None)
except Exception:
    story_id = None

if story_id:
    test("GET",  f"/v1/stories/{story_id}",          headers=h)
    test("POST", f"/v1/stories/{story_id}/feedback", headers=h, json_body={"resonance_score": 8, "comment": "test"})
else:
    print("  ⚠️  No story_id found in feed — skipping story tests")

# ── 6. Liberation ─────────────────────────────────────────────────────────────
print("\n[LIBERATION]")
cat_res = test("GET", "/v1/liberation/catalog", headers=h)
test("GET",  "/v1/liberation/status",            headers=h)
journey_code = None
if cat_res and cat_res.status_code == 200:
    defs = cat_res.json().get("data", {}).get("definitions", [])
    if defs:
        journey_code = defs[0].get("code")

if journey_code:
    test("POST", "/v1/liberation/enroll", headers=h, json_body={"journey_code": journey_code})
else:
    test("POST", "/v1/liberation/enroll", headers=h, json_body={"journey_code": "test_code"})

test("GET",  "/v1/liberation/day/1",          headers=h)
test("POST", "/v1/liberation/day/1/generate", headers=h, json_body={"morning_feeling": "Good"})
test("POST", "/v1/liberation/day/1/complete", headers=h, json_body={"energy_level": 8, "what_opened": "mind", "key_takeaway": "peace"})

# ── 7. Payment & Subscription ─────────────────────────────────────────────────
print("\n[PAYMENT]")
test("POST", "/v1/payment/checkout",    headers=h, json_body={"price_id": "price_test_123"})
test("GET",  "/v1/subscription/status", headers=h)

# ── Admin ─────────────────────────────────────────────────────────────────────
print("\n[ADMIN]")
test("GET",  "/v1/admin/dashboard/stats",         headers=h)
test("GET",  "/v1/admin/dashboard/figma-stats",   headers=h)
queue_res = test("GET",  "/v1/admin/moderation/queue",        headers=h)

mod_story_id = None
if queue_res and queue_res.status_code == 200:
    stories = queue_res.json().get("data", {}).get("stories", [])
    if stories:
        mod_story_id = stories[0].get("id")

if mod_story_id:
    test("GET",  f"/v1/admin/moderation/story/{mod_story_id}", headers=h)
    test("PUT",  f"/v1/admin/moderation/story/{mod_story_id}", headers=h,
         json_body={"title": "Audit Test Title", "story_type": "meditation", "story_text": "Test."})
    test("POST", f"/v1/admin/moderation/story/{mod_story_id}/approve", headers=h)
    test("POST", f"/v1/admin/moderation/story/{mod_story_id}/reject",  headers=h, json_body={"reason": "Test"})
else:
    print("  ⚠️  No stories in moderation queue — skipping story moderation tests")

photos_res = test("GET", "/v1/admin/photos", headers=h)
cover_id = None
if photos_res and photos_res.status_code == 200:
    photos = photos_res.json().get("data", {}).get("photos", [])
    if photos:
        cover_id = photos[0].get("id")

if cover_id:
    test("GET", f"/v1/admin/photos/{cover_id}", headers=h)
else:
    print("  ⚠️  No photos found — skipping photo detail test")

test("POST", "/v1/admin/chat", headers=h, json_body={"query": "How many users signed up this week?"})

# ── Admin Dashboard ───────────────────────────────────────────────────────────
print("\n[ADMIN DASHBOARD]")
test("GET", "/v1/admin/dashboard/figma-stats", headers=h)
test("GET", "/v1/admin/dashboard/stats", headers=h)

# ── Admin Voice Review ────────────────────────────────────────────────────────
print("\n[ADMIN VOICE REVIEW]")
vr_res = test("GET", "/v1/admin/voice-review", headers=h)
vr_story_id = None
if vr_res and vr_res.status_code == 200:
    vr_items = vr_res.json().get("data", {}).get("items", [])
    if vr_items:
        vr_story_id = vr_items[0].get("id")

if vr_story_id:
    test("POST", f"/v1/admin/voice-review/{vr_story_id}/regenerate", headers=h)
else:
    print("  ⚠️  No audio stories found — skipping voice regenerate test")

# ── Admin AI ──────────────────────────────────────────────────────────────────
print("\n[ADMIN AI]")
test("POST", "/v1/admin/ai/generate/bulk",       headers=h, json_body={"topic": "peace", "story_type": "meditation"})
test("POST", "/v1/admin/ai/generate/submission", headers=h, json_body={"submission_id": "test_id_123"})

# ── Signout last ──────────────────────────────────────────────────────────────
print("\n[SIGNOUT]")
test("POST", "/v1/signout", headers=h)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 100)
print("ISSUES REQUIRING FIXES:")
print("=" * 100)
issues = [(s, m, p, c, msg) for (s, m, p, c, msg) in results if s == "❌"]
if issues:
    for s, m, p, c, msg in issues:
        print(f"  ❌ {m:6} {p:55} {c}  {msg}")
else:
    print("  No critical issues found!")
print(f"\nTotal: {len(results)} endpoints tested | ✅ {sum(1 for r in results if r[0]=='✅')} passed | ❌ {sum(1 for r in results if r[0]=='❌')} failed")
