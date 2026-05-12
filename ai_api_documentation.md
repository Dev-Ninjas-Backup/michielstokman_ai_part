# AI API Documentation (Swagger Examples)

This document provides exact request and response JSON payloads for all AI-powered endpoints, perfectly matching the Swagger UI schemas. All responses are wrapped in a standard `ApiResponse` wrapper, where the actual data resides inside the `"data"` key.

---

## 1. Resonance Generation

**Endpoint:** `POST /v1/ai/resonance`
**Description:** Generates a deep, reflective journaling question based on a user's emotional state after listening to a track.

**Example Request:**
```json
{
  "track_id": "trk_12345",
  "touch_score": 9.2,
  "resonance_tags": ["Voice", "Liberation Moment", "Felt Seen"],
  "feedback_text": "That moment about the grandmother really touched me."
}
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Resonance question generated successfully",
  "data": {
    "journaling_question": "What specific fear surfaced in your body during that moment of tension, and how can you hold space for it?"
  }
}
```

---

## 2. Personalised Story Generation

**Endpoint:** `POST /v1/ai/story/generate`
**Description:** Queues a background job to write and voice a highly personalized story. Most fields are optional and fetched from the user's profile.

**Example Request:**
```json
{
  "story_type": "confession",
  "title": "Finding Peace in Solitude",
  "first_name": "Sarah",
  "story_input": "I have been feeling a lot of pressure at work lately, and I find myself snapping at the people I love. I want to explore why I'm pushing people away when I need them most.",
  "growth_areas": ["Self-Acceptance", "Forgiveness", "Patience"],
  "life_phase": "Deepening",
  "tags": ["work stress", "relationships", "inner peace"],
  "high_intensity": false
}
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Story generation queued",
  "data": {
    "story_id": "123e4567-e89b-12d3-a456-426614174000",
    "job_id": "987fcdeb-51a2-43d7-9012-34567890abcd",
    "title": null,
    "story_text": "",
    "audio_path": null,
    "message": "Story generation queued. Audio is being processed."
  }
}
```

---

## 3. Liberation Journey Daily AI Exercise

**Endpoint:** `POST /v1/liberation/day/{day}/generate`
**Description:** Generates the specific 10-minute AI exercise and greeting tailored to the user's morning feeling. (Executes synchronously).

**Example Request (Day 1):**
```json
{
  "morning_feeling": "I woke up feeling anxious and my chest is tight."
}
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Daily exercise generated",
  "data": {
    "day_number": 1,
    "day_theme": "Recognizing Attachment Patterns",
    "ai_greeting": "Good morning. I sense the anxiety sitting heavily in your chest today...",
    "ai_exercise_text": "Find a quiet space. Place your hand over your chest and breathe deeply into the tightness...",
    "ai_why_text": "We do this because recognizing the physical sensation of anxiety is the first step to detaching from it."
  }
}
```

---

## 4. Admin Bulk Generation

**Endpoint:** `POST /v1/admin/ai/generate/bulk`
**Description:** Queues a background job to write a generic template story for the catalog based on a topic.

**Example Request:**
```json
{
  "topic": "The feeling of finding peace after a chaotic week.",
  "story_type": "meditation",
  "format": "audio_script"
}
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Bulk generation job queued",
  "data": {
    "job_id": "555fca9c-a1cf-48f1-989a-6b89b1658911",
    "message": "Bulk generation job queued successfully."
  }
}
```

---

## 5. Admin Submission Generation (Custom Journeys)

**Endpoint:** `POST /v1/admin/ai/generate/submission`
**Description:** Queues a background job to dynamically construct a 7-day or N-day curriculum (Blueprint) for a custom journey requested by a user.

**Example Request:**
```json
{
  "submission_id": "777e4567-e89b-12d3-a456-426614174777"
}
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Submission generation job queued",
  "data": {
    "job_id": "222fcdeb-51a2-43d7-9012-34567890ab22",
    "message": "Submission generation job queued successfully."
  }
}
```

---

## 6. Background Job Polling

**Endpoint:** `GET /v1/admin/ai/status/{job_id}`
**Description:** Polls the database to check the status of any background generation (Story, Bulk, or Submission).

**Example Request:** 
*No JSON Body required. Pass `job_id` in the URL path.*

**Example Response (Still Processing):**
```json
{
  "status": "success",
  "message": "Job status retrieved",
  "data": {
    "job_id": "987fcdeb-51a2-43d7-9012-34567890abcd",
    "status": "processing",
    "title": null,
    "audio_path": null,
    "story_text": null
  }
}
```

**Example Response (Completed - Story):**
```json
{
  "status": "success",
  "message": "Job status retrieved",
  "data": {
    "job_id": "987fcdeb-51a2-43d7-9012-34567890abcd",
    "status": "completed",
    "title": "The Weight We Carry",
    "audio_path": "media/audio/123e4567-e89b-12d3.mp3",
    "story_text": "You stand at the edge of the water, feeling the cool breeze against your skin..."
  }
}
```

**Example Response (Completed - Liberation Submission):**
```json
{
  "status": "success",
  "message": "Job status retrieved",
  "data": {
    "job_id": "222fcdeb-51a2-43d7-9012-34567890ab22",
    "status": "completed",
    "title": "7 Days to Letting Go",
    "audio_path": null,
    "story_text": "Liberation Journey Blueprint with 7 days."
  }
}
```
