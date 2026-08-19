# Member Story Workspace — Frontend Integration Guide

Everything a member needs to create, narrate, manage and share their own
Confessions and Meditations.

**Base URL:** `https://www.transformtoliberation.com`
All paths below are prefixed with `/v1`.

---

## 1. Basics you need first

### Auth

Every endpoint in this guide requires a logged-in member. Send the JWT from
`POST /v1/login` on every request:

```
Authorization: Bearer <access_token>
```

### Response envelope

Every response — success or error — has the same shape:

```json
{
  "status": 200,
  "success": true,
  "message": "Stories retrieved",
  "data": { }
}
```

Always read your payload from `data`. On errors `success` is `false`, `data` is
`null`, and `message` holds text you can show the user directly.

### Status codes worth handling

| Code | Meaning |
|---|---|
| `200` | Done |
| `201` | Custom voice created |
| `202` | Accepted — work is running in the background, start polling |
| `401` | Token missing or expired → send to login |
| `402` | Out of daily credits → show the upgrade prompt |
| `404` | Not found, **or** not this member's story |
| `409` | Wrong state (e.g. story still generating, already withdrawn) |
| `413` / `415` | Upload too large / wrong file type |
| `422` | Validation failed |
| `503` | An AI provider is unavailable — safe to retry |

> A story belonging to another member returns `404`, never `403`. Don't treat it
> as a permissions error in the UI; treat it as "doesn't exist".

### The two async patterns

Some actions return `202` because an LLM and text-to-speech run in the
background. **Do not wait on the response** — poll instead:

```
GET /v1/me/stories/{story_id}
```

until `generation_status` is `"completed"` (or `"failed"`). Poll every 3–5
seconds; a full generation typically takes 30–90 seconds.

---

## 2. Voice selection

### List the available voices

```
GET /v1/voices
```

```json
{
  "data": {
    "voices": [
      { "name": "Sophia",    "label": "Sophia",    "gender": "female", "language": "english", "description": "Soft, meditative and unhurried...", "is_custom": false },
      { "name": "Charlotte", "label": "Charlotte", "gender": "female", "language": "english", "description": "Gentle and close...",                "is_custom": false },
      { "name": "Calen",     "label": "Calen",     "gender": "male",   "language": "english", "description": "Resonant and magnetic...",           "is_custom": false },
      { "name": "Victoria",  "label": "Victoria",  "gender": "female", "language": "french",  "description": "Warm and calm...",                    "is_custom": false },
      { "name": "Anja",      "label": "Anja",      "gender": "female", "language": "english", "description": "Rich and expressive...",              "is_custom": false }
    ],
    "custom_voice": null,
    "default_voice": "Sophia"
  }
}
```

Build the picker from `voices`. Pass the **`name`** value (not `label`) as
`voice_name` in later requests. If `custom_voice` is not `null`, show it as an
extra option — selecting it means sending `use_custom_voice: true` instead of a
`voice_name`.

Omitting `voice_name` entirely is fine: the backend picks a voice matching the
member's profile.

### Member's own voice (optional feature)

```
GET    /v1/me/voice     → is a cloned voice on file?
POST   /v1/me/voice     → upload recordings and clone
DELETE /v1/me/voice     → remove it
```

All three return the same shape — branch your UI on `has_custom_voice`:

```json
{
  "data": {
    "has_custom_voice": true,
    "voice_name": "My Voice",
    "created_at": "2026-08-19T11:58:23.977625",
    "message": "Custom voice is ready to use for narration."
  }
}
```

Upload is `multipart/form-data` with one or more files under the field name
`recordings`:

```js
const form = new FormData();
form.append("recordings", file);              // repeat for multiple takes
// optional: ?display_name=Mara's%20Voice

const res = await fetch("/v1/me/voice?display_name=My%20Voice", {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form,                                  // do NOT set Content-Type
});
```

Guidance for the recording UI:

- Ask for **at least 60 seconds** of clear, single-speaker audio.
- Accepted types: `mp3`, `wav`, `m4a`, `ogg`, `webm`. Max 10 MB per file.
- Files under ~32 KB are rejected with `422` ("Recording is too short").

**Handle `503` gracefully.** Voice cloning depends on the ElevenLabs plan. If it
isn't enabled, this endpoint returns `503` with an explanatory `message`. Show
that message and keep the five predefined voices available — the rest of the
product works normally.

Deleting a cloned voice does **not** change audio already generated with it.

---

## 3. Creating a story

The member chooses the cover **on the create screen**, then one request
creates the story.

```
POST /v1/ai/story/generate
```

### Option A — AI-generated artwork (JSON)

Use this when the member picks *Generate for me*. Existing JSON clients keep
working with no change.

```json
{
  "story_type": "confession",
  "title": "The Room I Never Left",
  "first_name": "Mara",
  "story_input": "I stayed too long in a place that stopped being mine.",
  "growth_areas": ["Fear & Freedom"],
  "life_phase": "Deepening",
  "tags": ["silence", "leaving"],
  "high_intensity": false,

  "voice_name": "Charlotte",
  "use_custom_voice": false,
  "image_mode": "ai_generated"
}
```

`image_mode` can be omitted — it defaults to `ai_generated`.

### Option B — member's own image (multipart)

Use this when the member picks *Upload my own*. The file travels **in the same
request** as the story fields. Do not create the story first and upload later.

```js
const form = new FormData();
form.append("story_type", "confession");
form.append("title", "The Room I Never Left");
form.append("first_name", "Mara");
form.append("story_input", "I stayed too long in a place that stopped being mine.");
form.append("growth_areas", JSON.stringify(["Fear & Freedom"]));
form.append("tags", JSON.stringify(["silence", "leaving"]));
form.append("voice_name", "Charlotte");
form.append("image_mode", "user_uploaded");
form.append("image", file);               // JPEG, PNG or WebP, up to 8 MB

const res = await fetch("/v1/ai/story/generate", {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form,                             // do NOT set Content-Type
});
```

Attaching `image` is enough — the backend treats that as `user_uploaded` even
if `image_mode` is left off. Sending `image_mode: "user_uploaded"` **without**
the file returns `422`.

JPEG, PNG or WebP, up to 8 MB. Wrong type → `415`, too large → `413`.

Response (both options):

```json
{
  "data": {
    "story_id": "0122f531-ee92-42b4-9a6b-ac814ce6e413",
    "story_number": 4,
    "story_reference": "TTL-000004",
    "job_id": "33cb99ed-...",
    "voice_name": "Charlotte",
    "image_mode": "user_uploaded",
    "cover_image_url": "https://.../images/mine.png",
    "message": "Story generation queued with your uploaded cover..."
  }
}
```

`cover_image_url` is set immediately for an uploaded file. For AI artwork it
stays `null` until generation finishes — poll `GET /v1/me/stories/{story_id}`
for the finished cover.

Then poll `GET /v1/me/stories/{story_id}` until it completes.

Notes:

- `story_input` is required. `story_type` is `confession`, `meditation` or
  `transformation`.
- An unknown `voice_name` returns `422` — validate against `GET /v1/voices`.
- `use_custom_voice: true` without an uploaded recording returns `422`.
- Costs one daily credit. `402` means the member is out; check remaining credits
  with `GET /v1/dashboard/credits`.
- If generation fails the credit is refunded automatically.
- A member-uploaded cover is never replaced by AI artwork, including when the
  story is edited and regenerated.

`GET /v1/admin/ai/status/{job_id}` still works for polling and now requires
auth, but `GET /v1/me/stories/{story_id}` is richer — prefer it.

To swap artwork later, use the endpoints in [section 7](#7-story-artwork).

---

## 4. The member's library

```
GET /v1/me/stories?story_type=&submission_status=&generation_status=&page=1&limit=20
```

All filters are optional; each also accepts `all`.

| Filter | Values |
|---|---|
| `story_type` | `confession`, `meditation`, `transformation` |
| `submission_status` | `submitted`, `withdrawn`, `draft` |
| `generation_status` | `processing`, `completed`, `failed` |

```json
{
  "data": {
    "stories": [
      {
        "id": "0122f531-...",
        "story_number": 4,
        "story_reference": "TTL-000004",
        "title": "The Room I Never Left",
        "excerpt": "I stayed in that room long after the door opened. The quiet was not peace, it was practice…",
        "story_type": "confession",
        "cover_image_url": "https://.../images/abc.jpg",
        "audio_path": "https://.../audio/abc.mp3",
        "voice_name": "Charlotte",
        "audio_duration_seconds": 412,
        "generation_status": "completed",
        "moderation_status": "pending",
        "submission_status": "submitted",
        "has_social_intros": false,
        "created_at": "2026-08-19T11:58:23.977625"
      }
    ],
    "counts": { "all": 3, "draft": 0, "submitted": 2, "withdrawn": 1 },
    "meta": { "total": 3, "page": 1, "limit": 20, "totalPages": 1 }
  }
}
```

Use `counts` for tab badges and `meta` for pagination.

### Preview text on cards

`excerpt` is a ready-to-render one-line preview of the narrated story: around
120 characters, cut on a word boundary, with an ellipsis only when text was
actually removed. Line breaks are already collapsed, so it drops straight into a
card without any client-side trimming.

`GET /v1/dashboard/feed` returns the identical `excerpt` on each story item, so
the same card component works for the public feed and the member's own library.
The feed's older `description` field still carries the same value and is kept
only for backwards compatibility — prefer `excerpt` in new code.

`excerpt` is `null` while a story is still generating and on stories that
failed, since there is no text yet. Fall back to the title in that state. The
full text stays on the detail endpoint only, so lists stay small.

This returns the member's **own** stories only, including ones still processing,
awaiting moderation, or withdrawn — none of which appear in
`GET /v1/dashboard/feed`.

### Three statuses, three different meanings

Show these separately; they are not interchangeable.

| Field | Owner | Meaning |
|---|---|---|
| `generation_status` | System | Is the AI done? `processing` / `completed` / `failed` |
| `moderation_status` | Admin | Review outcome: `pending` / `approved` / `rejected` / `flagged` |
| `submission_status` | **Member** | `submitted` (live) / `withdrawn` (pulled by the member) |

A useful label mapping:

- `processing` → "Creating your story…" (disable edit/narrate/withdraw actions)
- `failed` → "Something went wrong" + offer retry via `PATCH`
- `completed` + `pending` → "In review"
- `completed` + `approved` → "Published"
- `completed` + `rejected` → "Not approved" (show `moderation_notes`)
- `withdrawn` → "Withdrawn" + offer Resubmit

### Story detail

```
GET /v1/me/stories/{story_id}
```

Everything in the list item, plus:

| Field | Use for |
|---|---|
| `story_text` | **The AI-narrated story** — the read-along text |
| `story_input` | **The member's own original submission**, untouched |
| `alignment` | Word-level timings `[{word, start, end}]` for karaoke highlighting |
| `social_intros` | `{instagram, facebook, spotify}` or `null` |
| `uses_custom_voice` | Whether their cloned voice narrated it |
| `image_source` | `ai_generated` / `user_uploaded` / `admin_default` |
| `regeneration_count` | How many times they've re-run the AI |
| `moderation_notes` | Rejection reason, when present |
| `withdrawn_at` | When the member withdrew it, else `null` |
| `growth_areas`, `tags`, `life_phase`, `high_intensity` | Prefill the edit form |

Render "Listen" from `audio_path`, "Read" from `story_text`, and offer the
original submission separately from `story_input`.

Both `audio_path` and `cover_image_url` come back as fully-qualified URLs —
use them directly, don't prepend a base.

### Story number

Show `story_reference` (`"TTL-000004"`) as the member-visible identifier. Keep
using `id` (the UUID) for all API calls. `story_number` is the raw integer if
you need to sort or search by it.

---

## 5. Editing and regenerating

```
PATCH /v1/me/stories/{story_id}
```

Send only the fields that changed:

```json
{
  "story_input": "I finally described the room out loud.",
  "title": "The Room I Never Left",
  "voice_name": "Sophia",
  "regenerate": true
}
```

Accepted fields: `title`, `story_input`, `story_type`, `growth_areas`,
`life_phase`, `tags`, `high_intensity`, `voice_name`, `use_custom_voice`,
`regenerate`.

Two behaviours depending on `regenerate` (defaults to `true`):

| `regenerate` | HTTP | What happens |
|---|---|---|
| `true` | `202` | Edited input goes back through the AI prompt and is re-narrated. Poll until `completed`, then let the member preview the new text and audio. |
| `false` | `200` | Metadata-only correction. No AI call, returns immediately. |

Either way the story returns to `moderation_status: "pending"`, since the
content changed.

On regeneration: `regeneration_count` increments, and any existing
`social_intros` are cleared (they described the old text). A cover the member
uploaded themselves is **kept**; AI-generated covers are refreshed.

Errors: `409` if the story is still processing, `422` if `story_input` is blank.

### Re-narrate without rewriting

Lets a member audition voices on a finished story. The text is untouched and
**no credit is charged**.

```
POST /v1/me/stories/{story_id}/narrate
```

```json
{ "voice_name": "Calen" }
```

or

```json
{ "use_custom_voice": true }
```

Returns `202`. Poll until `generation_status` is `completed`, then reload the
player from the new `audio_path`. Note `alignment` changes too — re-fetch it if
you're highlighting words.

Sending neither field returns `422`.

---

## 6. Withdraw and resubmit

```
POST /v1/me/stories/{story_id}/withdraw
POST /v1/me/stories/{story_id}/resubmit
```

```json
{
  "data": {
    "story_id": "0122f531-...",
    "story_reference": "TTL-000004",
    "submission_status": "withdrawn",
    "message": "Story withdrawn. It is no longer publicly visible."
  }
}
```

**Withdraw** removes the story from the public feed and the moderation queue,
but keeps it in the member's library. The member can then submit a new
Confession or Meditation in its place. `409` if already withdrawn.

**Resubmit** puts it back and sends it for review again — expect
`moderation_status` to reset to `pending`. `409` if the story isn't withdrawn.

Withdraw is reversible and is what you should offer by default. For permanent
removal:

```
DELETE /v1/me/stories/{story_id}
```

This deletes the row, the audio and the cover art. Confirm with the member
first — it cannot be undone.

---

## 7. Story artwork

Each story carries its own cover image, used everywhere it appears including
social sharing. The member picks the source **when they create the story** —
JSON for AI artwork, or multipart with `image` for their own file.

`image_source` on the story tells you where the current artwork came from:
`ai_generated`, `user_uploaded`, or `admin_default` (the standard image for that
story type, used as a fallback).

The endpoints below are only for **changing** artwork after creation.

### Member uploads their own

```
POST /v1/me/stories/{story_id}/image
```

`multipart/form-data`, field name `image`:

```js
const form = new FormData();
form.append("image", file);

await fetch(`/v1/me/stories/${storyId}/image`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form,
});
```

JPEG, PNG or WebP, up to 8 MB. Wrong type → `415`, too large → `413`.

An uploaded image sets `image_source: "user_uploaded"` and is preserved across
regenerations, so the member never loses their own artwork.

### Generate artwork from the story

```
POST /v1/me/stories/{story_id}/image/generate
```

Synchronous (can take 30–60 seconds — show a spinner). The prompt is derived
from the story's own content and follows the palette and collage composition
defined for its type:

- **Confession** — blush pink and warm paper, hot pink accents
- **Meditation** — butter yellow and sage green on aged card
- **Transformation** — lavender and dusty violet

Both endpoints return:

```json
{
  "data": {
    "story_id": "0122f531-...",
    "cover_image_url": "https://.../images/abc.jpg",
    "image_source": "user_uploaded",
    "message": "Cover image updated."
  }
}
```

`503` means image generation isn't configured on the server; `502` means the
provider failed — offer a retry or the upload path instead.

---

## 8. Sharing to Instagram, Facebook and Spotify

### One call gets you everything

```
GET /v1/me/stories/{story_id}/share
```

```json
{
  "data": {
    "story_id": "0122f531-...",
    "story_number": 4,
    "story_reference": "TTL-000004",
    "title": "The Room I Never Left",
    "story_type": "confession",
    "author_name": "Mara",
    "cover_image_url": "https://.../images/abc.jpg",
    "audio_url": "https://.../audio/abc.mp3",
    "audio_duration_seconds": 412,
    "share_url": "https://www.transformtoliberation.com/stories/0122f531-...",
    "intros": {
      "instagram": "Some doors open long before we walk through them. Listen.",
      "facebook": "A confession about the quiet we mistake for peace, and the slow work of leaving it.",
      "spotify": "This is a confession about the rooms we stay in. It moves slowly, and it does not resolve..."
    },
    "generated_at": "2026-08-19T11:58:23.977625"
  }
}
```

The introductions are written on the first request, so this call may take a few
seconds initially and is fast afterwards.

### What each intro is for

| Platform | Length | Use |
|---|---|---|
| `instagram` | ≤ 220 chars, may end with up to 3 hashtags | Caption / story teaser |
| `facebook` | ≤ 400 chars, no hashtags | Post teaser |
| `spotify` | 100–180 words | Show notes, or read aloud as an intro track |

The `cover_image_url` is the same artwork shown on the website and PWA, so posts
stay visually consistent with the app. Pair it with `share_url` for the link and
`audio_url` for the audio itself.

### Rewriting the intros

```
POST /v1/me/stories/{story_id}/social-intros?force=true
```

Returns the full story detail with fresh `social_intros`. Without `force=true`
existing intros are returned unchanged. Use `has_social_intros` on the list item
to show a "Ready to share" badge without fetching the whole package.

Requires `story_text` to exist — `409` if the story hasn't generated yet.

---

## 9. Suggested screen flow

**Create**

1. `GET /v1/voices` → render the voice picker
2. `GET /v1/dashboard/credits` → show remaining credits
3. Ask how they want the artwork: *Generate for me* or *Upload my own*
4. `POST /v1/ai/story/generate` — JSON for AI art, or multipart with `image`
   for their own file. One request, not two.
5. Poll `GET /v1/me/stories/{id}` until `completed`
6. Show player (`audio_path` + `story_text` + `alignment`) and artwork

**My Stories**

1. `GET /v1/me/stories` → grid with `counts` tabs
2. Per card: `story_reference`, cover, `excerpt`, duration, the three status labels
3. Row actions: Edit · Change voice · Artwork · Share · Withdraw · Delete

**Story detail**

- Tabs: *Listen* (`audio_path`), *Read* (`story_text`), *My original* (`story_input`)
- Voice switcher inline → `POST .../narrate`, then reload audio
- *Share* panel → `GET .../share`, one copy button per platform

**Edit**

- Prefill from detail, `PATCH` with `regenerate: true`
- Warn that editing sends the story back for review
- Show progress, then a before/after preview of text and audio

---

## 10. Quick endpoint reference

| Method | Path | Notes |
|---|---|---|
| `GET` | `/v1/voices` | Voice options + member's cloned voice |
| `GET` | `/v1/me/voice` | Cloned voice status |
| `POST` | `/v1/me/voice` | Upload recordings → clone · `201` · multipart `recordings` |
| `DELETE` | `/v1/me/voice` | Remove cloned voice |
| `POST` | `/v1/ai/story/generate` | Create story. JSON = AI cover. Multipart `image` = own cover. |
| `GET` | `/v1/me/stories` | Own library · filters + pagination · cards include `excerpt` |
| `GET` | `/v1/me/stories/{id}` | Full detail · also the polling endpoint |
| `PATCH` | `/v1/me/stories/{id}` | Edit · `202` when regenerating, `200` when not |
| `DELETE` | `/v1/me/stories/{id}` | Permanent delete |
| `POST` | `/v1/me/stories/{id}/narrate` | Re-narrate in another voice · `202` · free |
| `POST` | `/v1/me/stories/{id}/withdraw` | Unpublish, keep in library |
| `POST` | `/v1/me/stories/{id}/resubmit` | Republish, returns to review |
| `POST` | `/v1/me/stories/{id}/image` | Replace cover after creation · multipart `image` |
| `POST` | `/v1/me/stories/{id}/image/generate` | Generate cover from story |
| `POST` | `/v1/me/stories/{id}/social-intros` | Write intros · `?force=true` to redo |
| `GET` | `/v1/me/stories/{id}/share` | Full Meta/Spotify share package |

Live schemas and a request sandbox: **`/docs`**.
