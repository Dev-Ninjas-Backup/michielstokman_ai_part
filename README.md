# Transform to Liberation API

Simple endpoint reference for developers.

## Base Rules

- API version prefix: `/v1` (except `/health`)
- Auth for protected routes: `Authorization: Bearer <token>`
- Some endpoints are admin-only

## System

- `GET /health` - Service health check
- `GET /v1/hello` - Quick test endpoint

## Authentication

- `POST /v1/signup` - Register new user
- `POST /v1/login` - Login and get access token
- `POST /v1/signout` - Sign out and invalidate current token

## Profile

- `GET /v1/me/profile` - Get current user profile
- `PUT /v1/me/profile` - Create or update current user profile

## AI Features

- `GET /v1/ai/search` - Semantic track search from user query
- `POST /v1/ai/resonance` - Generate resonance question
- `POST /v1/ai/story/generate` - Start async story generation job
- `GET /v1/admin/ai/status/{job_id}` - Poll story generation status
- `POST /v1/admin/ai/generate/bulk` - Admin bulk generation job
- `POST /v1/admin/ai/generate/submission` - Admin generation from submission
- `POST /v1/ai/rag/ingest/all` - Admin full RAG re-index
- `POST /v1/ai/rag/ingest/new` - Admin incremental RAG ingest

## Dashboard

- `GET /v1/dashboard/feed` - Discovery feed with stories and liberation card
- `GET /v1/dashboard/credits` - Current user credit status
- `GET /v1/dashboard/recommendations` - Personalized book recommendations
- `GET /v1/stories/{story_id}` - Story detail with feedback stats

## Feedback

- `POST /v1/stories/{story_id}/feedback` - Create or update story feedback

## Liberation Journey

- `POST /v1/liberation/enroll` - Start or resume 7-day journey
- `GET /v1/liberation/status` - Full journey progress
- `POST /v1/liberation/day/{day}/generate` - Generate daily exercise
- `POST /v1/liberation/day/{day}/complete` - Complete day and unlock next
- `GET /v1/liberation/day/{day}` - Day detail for review/playback
- `GET /v1/liberation/feed-card` - Journey card for discovery grid

## Payment

- `POST /v1/payment/checkout/start` - Start checkout session
- `POST /v1/payment/webhook` - Payment provider webhook
- `GET /v1/payment/history/{user_id}` - User payment history

## Subscription

- `GET /v1/subscription/plans` - List available plans
- `GET /v1/subscription/{user_id}` - Get user subscription status
- `POST /v1/subscription/cancel` - Cancel active subscription

## Admin Dashboard

- `GET /v1/admin/dashboard/stats` - Real admin dashboard metrics
- `GET /v1/admin/dashboard/demo` - Legacy admin demo route

## Admin Moderation

- `GET /v1/admin/moderation/queue` - Moderation queue
- `GET /v1/admin/moderation/story/{story_id}` - Story detail for moderation
- `PUT /v1/admin/moderation/story/{story_id}` - Update story details
- `POST /v1/admin/moderation/story/{story_id}/approve` - Approve story
- `POST /v1/admin/moderation/story/{story_id}/reject` - Reject story
- `DELETE /v1/admin/moderation/story/{story_id}` - Delete story
