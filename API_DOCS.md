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

## 2. Admin - Dashboard & Metrics

### `GET /v1/admin/dashboard/figma-stats`
Fetch platform metrics aligned with Figma designs (All, Confessions, Meditations, Journey).

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Figma dashboard stats fetched",
  "data": {
    "all": { "count": 150, "delta": 12 },
    "confessions": { "count": 45, "delta": -2 },
    "meditations": { "count": 60, "delta": 8 },
    "journey": { "count": 45, "delta": 5 },
    "latest_activity": [
      {
        "id": "uuid",
        "email": "user@example.com",
        "action": "Generated Story",
        "timestamp": "2026-05-12T10:00:00Z"
      }
    ]
  }
}
```

---

### `POST /v1/admin/chat`
Ask natural language questions about platform metrics (SuperGrok Powered).

**Request Body:**
```json
{
  "query": "Show me the top resonance content this week"
}
```

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Admin AI response generated",
  "data": {
    "answer": "Here are the top stories by resonance:\n1. \"Morning Calm\" — 9.2 pulse (45 reflections)\n2. \"Deep Healing\" — 8.8 pulse (32 reflections)"
  }
}
```

---

## 3. Admin - Content Moderation

### `GET /v1/admin/moderation/queue`
Fetch the moderation queue with counts for each status tab.

**Query Params:**
- `status_filter`: `pending` | `approved` | `rejected` | `flagged` | `all`
- `search`: search by title or author email
- `limit`, `offset`: pagination

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Moderation queue fetched",
  "data": {
    "stories": [
      {
        "id": "uuid",
        "title": "My Transformation",
        "story_type": "Journey",
        "author": "user@example.com",
        "created_at": "12 May 26",
        "moderation_status": "Pending",
        "cover_image_url": "https://..."
      }
    ],
    "all": 150,
    "pending": 12,
    "flagged": 2,
    "approved": 120,
    "rejected": 16
  }
}
```

---

### `PUT /v1/admin/moderation/story/{story_id}`
Edit story content before approval.

**Request Body:**
```json
{
  "title": "Updated Title",
  "story_text": "Updated content...",
  "story_type": "meditation"
}
```

---

### `POST /v1/admin/moderation/story/{story_id}/approve`
Approve a story for public display.

---

### `POST /v1/admin/moderation/story/{story_id}/reject`
Reject a story with internal notes.

**Request Body:**
```json
{
  "reason": "Violates safety guidelines"
}
```

---

## 4. Admin - Voice Review

### `GET /v1/admin/voice-review`
List stories with generated audio for quality review.

**Response `200`:**
```json
{
  "status": 200,
  "success": true,
  "message": "Voice review list fetched",
  "data": {
    "items": [
      {
        "id": "uuid",
        "title": "Night Reflection",
        "story_type": "Meditations",
        "voice_name": "Aria (Warm)",
        "audio_duration": "3:45",
        "created_at": "11 May 26",
        "audio_path": "media/audio/..."
      }
    ],
    "total": 45
  }
}
```

---

### `POST /v1/admin/voice-review/{story_id}/regenerate`
Trigger audio regeneration if the voice quality is poor.

---

## 5. Admin - Photo Management

### `GET /v1/admin/photos`
List all cover images available in the library.

### `POST /v1/admin/photos`
Upload a new cover image (Multipart Form).

---

## 6. Admin - AI Bulk Generation

### `POST /v1/admin/ai/generate/bulk`
Trigger bulk generation of stories for a specific topic/type.

**Request Body:**
```json
{
  "topic": "inner peace",
  "story_type": "meditation",
  "count": 5
}
```

---

## Error Codes

| Status | Code | Description |
|---|---|---|
| `401` | Unauthorized | Missing or invalid token |
| `403` | Forbidden | User is not an admin |
| `404` | Not Found | Resource does not exist |
| `422` | Validation Error | Invalid request parameters |
| `503` | Service Unavailable | External AI service (xAI/ElevenLabs) is down or keys missing |
