# Transform to Liberation — API Documentation

**Base URL:** `http://34.255.26.146:8000`  
**Interactive Docs:** [http://34.255.26.146:8000/docs](http://34.255.26.146:8000/docs)  
**Version:** `1.0.1`

---

## Authentication

All protected endpoints require the following header:

```
Authorization: Bearer <access_token>
```

Admin endpoints additionally require the user to have `is_admin: true`.

---

## 1. Auth Endpoints

### `POST /v1/signup`
Register a new user and receive a JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**Response `201`:**
```json
{
  "status": 201,
  "success": true,
  "message": "Signup successful",
  "data": {
    "access_token": "<jwt_token>",
    "token_type": "bearer",
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "is_active": true,
      "is_admin": false,
      "created_at": "2026-05-09T19:00:00"
    },
    "is_new_user": true
  }
}
```

---

### `POST /v1/login`
Login with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Login successful",
  "data": {
    "access_token": "<jwt_token>",
    "token_type": "bearer",
    "user": { "id": "uuid", "email": "user@example.com", "is_admin": false },
    "is_new_user": false
  }
}
```

---

### `POST /v1/social-login`
Login with Google or Apple token.

**Request Body:**
```json
{
  "provider": "google",
  "token": "google_id_token_here"
}
```

**Response `200`:** Same structure as `/v1/login`.

---

### `POST /v1/signout`
Invalidate the current JWT token.

**Headers:** `Authorization: Bearer <token>`  
**Body:** None

**Response `200`:**
```json
{ "status": 200, "success": true, "message": "Successfully signed out" }
```

---

### `POST /v1/auth/refresh`
Get a new access token for the current user.

**Headers:** `Authorization: Bearer <token>`  
**Body:** None

---

### `POST /v1/auth/forgot-password`
**Body:** None (placeholder — sends reset link if email exists)

### `POST /v1/auth/reset-password`
**Body:** None (placeholder)

### `POST /v1/auth/update-password`
**Body:** None (placeholder)

---

## 2. Profile Endpoints

### `PUT /v1/me/profile`
Create or update the current user's profile. Call this after signup onboarding.

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "gender": "female",
  "age": 28,
  "relationship_status": "single",
  "slider_desire_relationship": 8,
  "slider_fear_loneliness": 5,
  "slider_desire_freedom": 7,
  "slider_fear_rejection": 3,
  "deepest_desire_fear": "I want to feel truly seen and understood.",
  "specific_trigger": "A recent breakup left me feeling lost.",
  "emotional_context": "Anxiety, confusion, but also hope.",
  "country_city": "London, UK",
  "life_phase": "career transition"
}
```

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Profile updated successfully",
  "data": { "id": "uuid", "gender": "female", "age": 28, "..." : "..." }
}
```

---

### `GET /v1/me/profile`
Fetch the current user's profile.

**Headers:** `Authorization: Bearer <token>`  
**Body:** None

> Returns `404` if profile has not been created yet — call `PUT /v1/me/profile` first.

---

### `GET /v1/auth/profile`
Alias for `GET /v1/me/profile`. Same response.

---

## 3. Dashboard Endpoints

All require `Authorization: Bearer <token>`.

### `GET /v1/dashboard/feed`
Returns the main discovery grid (stories + liberation journey card).

**Body:** None

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Discovery feed loaded",
  "data": {
    "items": [
      { "card_type": "story", "title": "...", "audio_path": "...", "..." : "..." }
    ]
  }
}
```

---

### `GET /v1/dashboard/credits`
Returns the user's daily credit status.

**Response `200`:**
```json
{
  "data": {
    "is_premium": false,
    "daily_credits_remaining": 3,
    "max_daily_credits": 3,
    "message": "3/3 credits remaining today."
  }
}
```

---

### `GET /v1/dashboard/recommendations`
Returns personalised book recommendations.

---

## 4. AI Endpoints

### `POST /v1/ai/story/generate`
Trigger AI story generation. Returns a `job_id` immediately — poll for status.

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "story_type": "meditation",
  "emotional_context": "overwhelmed and burned out from work",
  "specific_trigger": "a difficult meeting with my manager",
  "life_phase": "career growth"
}
```

**Response `200`:**
```json
{
  "data": { "job_id": "84be1e3c-c155-41eb-b462-04a938103156", "status": "queued" }
}
```

---

### `GET /v1/admin/ai/status/{job_id}`
Poll the status of a generation job. Keep polling until `status == "completed"`.

**URL Param:** `job_id` — from the generate response.

**Response `200`:**
```json
{
  "data": { "status": "completed", "story_id": "uuid", "audio_url": "https://..." }
}
```

---

### `POST /v1/ai/resonance`
Generate a personalised journaling question after a user listens to a story.

**Request Body:**
```json
{
  "track_id": "story-uuid-here",
  "touch_score": 8
}
```

---

### `GET /v1/ai/search`
Search for stories or content via AI.

**Query Params:** `q=your search query`

---

## 5. Stories

### `GET /v1/stories/{story_id}`
Fetch full story text, audio URL, and community stats.

**URL Param:** `story_id`

---

### `POST /v1/stories/{story_id}/feedback`
Submit user feedback/reaction to a story.

**Request Body:**
```json
{
  "resonance_score": 9,
  "comment": "This really spoke to me."
}
```

---

## 6. Liberation Journey

### `GET /v1/liberation/catalog`
List all available liberation journeys.

**Response `200`:**
```json
{
  "data": { "definitions": [...], "total": 5 }
}
```

---

### `GET /v1/liberation/status`
Get the user's active journey progress/tree.

> Returns `404` if not enrolled yet.

---

### `POST /v1/liberation/enroll`
Enroll in a liberation journey.

**Request Body:**
```json
{
  "journey_code": "journey-code-from-catalog"
}
```

---

### `GET /v1/liberation/day/{day}`
Fetch content for a specific day of the journey.

**URL Param:** `day` — e.g. `1`

---

### `POST /v1/liberation/day/{day}/generate`
Generate the morning check-in story for a given day.

**URL Param:** `day` — e.g. `1`  
**Body:** None

---

### `POST /v1/liberation/day/{day}/complete`
Mark the day as complete and unlock the next day.

**URL Param:** `day` — e.g. `1`  
**Body:** None

---

## 7. Payment & Subscription

### `POST /v1/payment/checkout`
Create a Stripe checkout session.

**Request Body:**
```json
{
  "price_id": "price_stripe_id_here"
}
```

### `GET /v1/subscription/status`
Get the current user's subscription status.

---

## 8. Admin Endpoints

> All admin endpoints require `Authorization: Bearer <token>` from an `is_admin: true` user.
>
> **Admin credentials:**  
> Email: `admin@transform.com`  
> Password: `AdminPassword123!`

---

### `GET /v1/admin/dashboard/stats`
Fetch platform-wide KPI metrics.

**Response `200`:**
```json
{
  "data": {
    "total_users": 18,
    "active_subscriptions": 0,
    "stories_generated_today": 3,
    "revenue_this_month": 0
  }
}
```

---

### `GET /v1/admin/moderation/queue`
List all stories pending moderation.

**Optional Query Params:**
- `moderation_status=pending` | `approved` | `rejected`
- `search=keyword`
- `limit=20` | `offset=0`

---

### `GET /v1/admin/moderation/story/{story_id}`
Fetch full story details for review.

---

### `PUT /v1/admin/moderation/story/{story_id}`
Update a story's content before approving.

**Request Body:**
```json
{
  "title": "Revised Story Title",
  "story_type": "meditation",
  "story_text": "Updated story content goes here."
}
```

---

### `POST /v1/admin/moderation/story/{story_id}/approve`
Approve a story for publication.

**Body:** None

---

### `POST /v1/admin/moderation/story/{story_id}/reject`
Reject a story with a reason.

**Request Body:**
```json
{
  "reason": "Content does not meet platform guidelines."
}
```

---

### `DELETE /v1/admin/moderation/story/{story_id}`
Permanently delete a story.

**Body:** None

---

### `GET /v1/admin/photos`
List all cover images/photos.

### `POST /v1/admin/photos`
Upload a new cover image (multipart form data).

**Form Fields:** `story_type`, `file`

### `GET /v1/admin/photos/{cover_id}`
Fetch details for a specific cover image.

### `PATCH /v1/admin/photos/{cover_id}`
Update a cover image or its status.

### `DELETE /v1/admin/photos/{cover_id}`
Delete a cover image.

---

### `POST /v1/admin/chat`
Ask a natural language question about platform metrics.

**Request Body:**
```json
{
  "query": "How many stories were generated this week?"
}
```

---

## Error Response Format

All errors follow this consistent structure:

```json
{
  "status": 422,
  "success": false,
  "message": "Field required",
  "data": null
}
```

| Status Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Created |
| `400` | Bad Request (e.g. email already exists) |
| `401` | Unauthorized (missing/invalid token) |
| `403` | Forbidden (not an admin) |
| `404` | Not Found |
| `422` | Validation Error (missing/wrong fields) |
| `500` | Internal Server Error |

---

## Quick Start

```bash
# 1. Login and get token
curl -X POST http://34.255.26.146:8000/v1/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@transform.com", "password": "AdminPassword123!"}'

# 2. Use the token in subsequent requests
curl http://34.255.26.146:8000/v1/dashboard/feed \
  -H "Authorization: Bearer <your_access_token>"
```
