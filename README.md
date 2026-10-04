# 🌿 Transform to Liberation API

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)
[![Astral uv](https://img.shields.io/badge/uv-Astral-DE5FE9?style=for-the-badge&logo=python)](https://github.com/astral-sh/uv)
[![Postgres](https://img.shields.io/badge/Postgres-SQLAlchemy-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)
[![Pinecone](https://img.shields.io/badge/Pinecone-Vector_DB-000000?style=for-the-badge)](https://www.pinecone.io/)
[![xAI](https://img.shields.io/badge/xAI-Grok--3-1DA1F2?style=for-the-badge)](https://x.ai/)
[![ElevenLabs](https://img.shields.io/badge/ElevenLabs-TTS_&_Cloning-FF6C37?style=for-the-badge)](https://elevenlabs.io/)
[![Playwright](https://img.shields.io/badge/Playwright-Headless_Chromium-2EAD33?style=for-the-badge&logo=playwright)](https://playwright.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker)](https://www.docker.com/)
[![AWS S3](https://img.shields.io/badge/AWS-S3-569A31?style=for-the-badge&logo=amazons3)](https://aws.amazon.com/s3/)
[![Stripe](https://img.shields.io/badge/Stripe-Payments-008CFF?style=for-the-badge&logo=stripe)](https://stripe.com/)

A premium, production-grade, AI-driven backend powering **Transform to Liberation**—an emotional transformation and therapeutic platform that dynamically crafts personalized healing narratives (Confessions, Meditations, Transformations), studio-grade voice narrations, custom voice clones, pixel-perfect dynamic artwork, 7-Day Liberation Journeys, and RAG-powered semantic book recommendations.

* **Production URL**: [https://www.transformtoliberation.com/](https://www.transformtoliberation.com/)
* **Interactive API Reference**: [https://www.transformtoliberation.com/docs](https://www.transformtoliberation.com/docs)

---

## 🏗️ Architecture & Server Routing

The system is deployed on an AWS EC2 instance reverse-proxied with **Nginx** and secured using SSL/TLS via **Let's Encrypt Certbot**.

```
                       [ HTTPS Ingress (Port 443) ]
                                    │
                            [ Nginx Reverse Proxy ]
                                    │
              ┌─────────────────────┴─────────────────────┐
              ▼                                           ▼
    [ Next.js Frontend ]                         [ FastAPI Backend ]
        Port 3000                                    Port 8000
   (Pages, UI, Audio Player)                (/v1/*, /health, /docs, /media/*)
```

### Nginx Routing Strategy
* **Frontend**: Dynamic UI routing handled by the Next.js service on port `3000`.
* **API Endpoints**: Gated behind the `/v1/` prefix and routed natively to the FastAPI backend service on port `8000`.
* **Interactive Swagger Documentation**: Exposed under `/docs` and OpenAPI schema under `/openapi.json` with direct Bearer / JWT token authentication.
* **Media Storage**: Audio (`/media/audio`) and image (`/media/images`) assets served locally or backed by **AWS S3**.

---

## ⚡ Tech Stack & Core Libraries

* **Core Framework**: [FastAPI](https://fastapi.tiangolo.com/) (0.135+) running on Python 3.13 with asynchronous endpoints and Pydantic v2 validation.
* **Package & Virtual Environment**: [Astral `uv`](https://github.com/astral-sh/uv) for ultra-fast dependency resolution and deterministic locking (`uv.lock`).
* **Database & ORM**: PostgreSQL with [SQLAlchemy 2.0](https://www.sqlalchemy.org/) and [Alembic](https://alembic.sqlalchemy.org/) migrations.
* **Vector Database**: [Pinecone](https://www.pinecone.io/) for high-dimensional semantic story and recommendation retrieval.
* **Large Language Model (LLM)**: [xAI SuperGrok](https://x.ai/) (`grok-3`, `grok-3-mini`) for dynamic narrative scripting, resonance journaling prompts, and marketing social copy.
* **Voice Narration & Cloning (TTS)**: [ElevenLabs](https://elevenlabs.io/) (`eleven_turbo_v2_5`) for lifelike studio voice synthesis and member custom voice cloning.
* **Cover Art Generation & Rendering**:
  * **HTML/CSS Template Engine**: Headless Chromium via [Playwright](https://playwright.dev/) capturing high-resolution 2160×2160 cover cards with authentic TTL typography and dynamic badges.
  * **AI Portrait & Image Models**: OpenAI (`gpt-image-2` / DALL-E) for emotional character portraits seamlessly composited into the cover layout.
* **Media & Cloud Storage**: [Amazon S3](https://aws.amazon.com/s3/) (`boto3`) for permanent audio and cover artwork storage with pre-signed / direct URLs.
* **Authentication & Social Logins**: Passlib/Bcrypt, PyJWT, and Firebase Admin SDK supporting Google and Apple social logins.
* **Billing & Subscriptions**: [Stripe](https://stripe.com/) webhooks, checkout sessions, and multi-tier subscription access control.

---

## 🌟 Core Engine Pipelines

### 1. The Story Generation Pipeline
Transforms member inputs (morning feelings, personal dilemmas, growth areas, life phase) into structured therapeutic audio experiences:
* **Three Narrative Types**: `confession`, `meditation`, and `transformation`.
* **Emotional Direction**: Enforces documentary intimacy, natural moments, and category-specific emotional arcs across 6 narrative dimensions (avoiding generic stock compositions).
* **Audio Synthesis**: Coordinates with ElevenLabs to render narration and word-level alignment metadata for synchronized frontend playback.
* **Asynchronous Execution**: Dispatched as background jobs with polling endpoints (`/v1/admin/ai/status/{job_id}`).

### 2. Dual-Engine Cover Art Generation
Controlled seamlessly via the `COVER_GENERATION_METHOD` environment variable:
* **`template` (Default & Client-Approved)**:
  * Generates an emotional character portrait matching the story's themes using OpenAI (`gpt-image-2` / `dalle`).
  * Injects story title, subtitle, confession excerpt, author name, age, gender, sexual orientation, and location into a pixel-perfect 2160×2160 HTML/CSS template (`app/cover_template/`).
  * Renders a pristine PNG snapshot headlessly via Playwright Chromium and saves it directly to AWS S3.
* **`dalle`**: Generates full scrapbook-style collage covers directly via OpenAI image models.
* **Interactive Style Previews**: Includes dedicated non-production endpoints (`/v1/test/cover-template-preview` and `/v1/test/confession-cover-style-preview`) for rapid testing without altering database state.

### 3. Voice Studio & Member Custom Voice Cloning
* **Curated Studio Voices**: Pre-configured narrator catalog with playable preview clips.
* **Custom Voice Cloning**: Members upload voice recordings (`POST /v1/me/voice`) to clone their own voice for narrative playback.
* **Zero-Credit Re-Narration**: Audition existing completed stories in any catalog or cloned voice without re-running the text prompt or consuming daily credits (`POST /v1/me/stories/{story_id}/narrate`).

### 4. Member Story Workspace (`/v1/me/stories`)
* **Private Story Catalog**: Members manage drafts, active pieces, withdrawn items, and moderation states.
* **Story Regeneration**: Update story inputs and trigger background re-writing and re-narration.
* **Dynamic Artwork Generation**: Generate story-specific cover art on demand from the story text.
* **Distribution & Sharing Suite**: Automatically synthesizes platform-tailored teasers for Meta (Instagram / Facebook) and spoken-word audio introductions for Spotify (`/v1/me/stories/{story_id}/share`).

### 5. 7-Day Premium Liberation Journey
* **Multi-Day Progressive Unlocks**: Step-by-step curriculum guiding users through emotional liberation.
* **Daily Check-Ins**: Users submit morning emotional states and receive tailored daily exercises.
* **Post-Exercise Reflections**: Captures energy sliders, cognitive shifts, and key takeaways before unlocking subsequent days.
* **Repeat & Restart**: Enables users to replay completed journeys with reset reflection logs.

### 6. RAG Semantic Search & Book Recommendations
* **Semantic Discovery**: Natural language vector query endpoint (`/v1/ai/search`) matching tracks by emotional resonance in Pinecone.
* **Tailored Book Recommendations**: Synthesizes book recommendations based on user emotional engagement and vector matches.
* **Admin Ingestion**: Automated indexing tools for bulk (`/ingest/all`), incremental (`/ingest/new`), and track vector sync (`/ingest/tracks`).

### 7. Multi-Asset Moderation & Admin Control Center
* **Three-Stage Granular Approval**: Dedicated approval gates for **written content**, **cover artwork**, and **narration voice**, or unified one-click publishing.
* **Voice Review Queue**: Specialized queue for monitoring generated audio and requesting single-click regenerations.
* **Photo Library Management**: S3 object management, image swapping, and categorization.
* **User & Subscription Admin**: Full user lifecycle management, role assignments, and subscription metrics.
* **Admin AI Database Assistant**: Natural language chat interface (`POST /v1/admin/chat`) allowing administrators to query database metrics and platform statistics using Grok.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
* **Python 3.13+**
* **Astral `uv`** (or standard Python virtual environment)
* **PostgreSQL** (running locally or via Docker)
* **Docker & Docker Compose** (optional, for containerized run)

### 2. Local Installation using Astral `uv`

```bash
# Clone the repository
git clone https://github.com/TashinMahmud/TransformToLiberation.git
cd TransformToLiberation

# Install Astral uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Unix/macOS
# or: pip install uv

# Create virtual environment and install all dependencies
uv venv
uv sync

# Install Playwright browser dependencies (required for HTML cover rendering)
uv run playwright install --with-deps chromium
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and configure your credentials:

```bash
cp .env.example .env
```

Key environment variables:
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `XAI_API_KEY` | xAI SuperGrok API Key for LLM text generation | `xai-...` |
| `LLM_MODEL` | SuperGrok model identifier | `grok-3` / `grok-3-mini` |
| `ELEVENLABS_API_KEY` | ElevenLabs API Key for voice TTS & cloning | `...` |
| `ELEVENLABS_MODEL_ID` | ElevenLabs TTS model | `eleven_turbo_v2_5` |
| `PINECONE_API_KEY` | Pinecone API Key for vector searches | `...` |
| `PINECONE_INDEX_NAME` | Pinecone vector index name | `stories-rag` |
| `COVER_GENERATION_METHOD` | Cover art pipeline (`template` or `dalle`) | `template` |
| `OPENAI_IMAGE_MODEL` | Image model for template portrait cutout | `gpt-image-2` |
| `OPENAI_API_KEY` | OpenAI API key for cover portrait generation | `sk-...` |
| `DB_USER` / `DB_PASSWORD` | PostgreSQL connection credentials | `postgres` / `secret` |
| `DB_HOST` / `DB_NAME` | PostgreSQL database location | `localhost` / `transform_liberation` |
| `AWS_ACCESS_KEY_ID` | AWS IAM key for S3 media bucket storage | `AKIA...` |
| `AWS_BUCKET_NAME` | AWS S3 Bucket Name for audio/images | `ttl-media-prod` |
| `STRIPE_API_KEY` | Stripe secret key for billing | `sk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | `whsec_...` |

### 4. Database Migrations

Apply Alembic migrations to initialize or update the database schema:

```bash
uv run alembic upgrade head
```

### 5. Running the Application

**Development Server (with Hot Reload):**
```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The interactive Swagger UI is available at: **[http://localhost:8000/docs](http://localhost:8000/docs)**.

**Running with Docker Compose:**
```bash
docker compose up --build -d
```

### 6. Running Tests

Execute the comprehensive test suite with `pytest`:

```bash
uv run pytest
```

---

## 🧭 Complete API Endpoint Reference

All endpoints return standardized JSON wrapped in an `ApiResponse`:
```json
{
  "status": 200,
  "success": true,
  "message": "Operation description",
  "data": { ... }
}
```

### 🔐 System & Authentication (`/v1`)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | System health check (LB/Uptime monitoring) | Public |
| `POST` | `/v1/signup` | Register a new user account & return JWT | Public |
| `POST` | `/v1/login` | Authenticate with email/password (JSON or Form) | Public |
| `POST` | `/v1/social-login` | Authenticate via Firebase ID token (Google/Apple) | Public |
| `POST` | `/v1/guest-login` | Create anonymous guest session (1 story/day limit) | Public |
| `POST` | `/v1/signout` | Invalidate current JWT token | Bearer Auth |
| `POST` | `/v1/auth/refresh` | Refresh an active or recently expired JWT | Bearer Auth |
| `GET` | `/v1/auth/profile` | Alias for user profile information | Bearer Auth |
| `POST` | `/v1/auth/forgot-password` | Request password reset email | Public |
| `POST` | `/v1/auth/reset-password` | Confirm password reset | Public |
| `POST` | `/v1/auth/update-password` | Update current account password | Bearer Auth |

### 👤 Profile & User Settings
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/me/profile` | Retrieve the authenticated user's profile | Bearer Auth |
| `PUT` | `/v1/me/profile` | Update profile fields (name, age, country, bio, sliders) | Bearer Auth |
| `PUT` | `/v1/me/profile/avatar` | Update profile avatar URL | Bearer Auth |

### 🔮 AI Generation & Search
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/v1/ai/story/generate` | Queue asynchronous story generation (JSON or audio) | Bearer Auth |
| `GET` | `/v1/admin/ai/status/{job_id}` | Poll generation job progress and audio/text outputs | Bearer Auth |
| `GET` | `/v1/ai/search` | Natural language semantic track search (`?q=...`) | Public (Rate Limited) |
| `POST` | `/v1/ai/resonance` | Generate deep journaling reflection question | Public (Rate Limited) |
| `POST` | `/v1/admin/ai/generate/bulk` | Queue admin bulk story catalog generation | Admin Only |
| `POST` | `/v1/admin/ai/generate/submission` | Queue AI generation from user submission | Admin Only |
| `POST` | `/v1/ai/rag/ingest/all` | Full vector re-indexing of all stories into Pinecone | Admin Only |
| `POST` | `/v1/ai/rag/ingest/new` | Incremental vector indexing of recent stories | Admin Only |
| `POST` | `/v1/ai/rag/ingest/tracks` | Vector indexing of approved liberation definitions | Admin Only |

### 🎙️ Voices & Member Story Workspace (`/v1/me/stories`)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/voices` | List available narrator voices + custom cloned voice | Bearer Auth |
| `GET` | `/v1/me/voice` | Retrieve custom voice cloning status | Bearer Auth |
| `POST` | `/v1/me/voice` | Upload audio samples to clone member's voice | Bearer Auth |
| `DELETE` | `/v1/me/voice` | Delete cloned custom voice | Bearer Auth |
| `GET` | `/v1/me/stories` | List authenticated member's stories (draft, active, etc.) | Bearer Auth |
| `GET` | `/v1/me/stories/{id}` | Retrieve full detail for a member's own story | Bearer Auth |
| `PATCH` | `/v1/me/stories/{id}` | Update story metadata with optional regeneration | Bearer Auth |
| `DELETE` | `/v1/me/stories/{id}` | Permanently delete member's story and media | Bearer Auth |
| `POST` | `/v1/me/stories/{id}/narrate` | Re-narrate story in a different voice (0 credits) | Bearer Auth |
| `POST` | `/v1/me/stories/{id}/withdraw` | Withdraw story from public feed and moderation | Bearer Auth |
| `POST` | `/v1/me/stories/{id}/resubmit` | Resubmit withdrawn story to moderation queue | Bearer Auth |
| `POST` | `/v1/me/stories/{id}/image/generate` | Generate fresh cover artwork from story content | Bearer Auth |
| `POST` | `/v1/me/stories/{id}/social-intros` | Synthesize Meta teasers and Spotify audio intros | Bearer Auth |
| `GET` | `/v1/me/stories/{id}/share` | Retrieve full distribution package for social sharing | Bearer Auth |

### 📊 Dashboard, Feeds & Feedback
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/dashboard/feed` | Discovery feed with filtering (type, sort, explicit) | Public / Guest |
| `GET` | `/v1/stories/{story_id}` | Full story detail & audio player view (with feedback stats) | Public / Guest (1/day) |
| `GET` | `/v1/dashboard/recommendations` | RAG-powered book recommendations via Grok + Pinecone | Bearer Auth |
| `GET` | `/v1/dashboard/credits` | Query remaining daily credits or premium status | Bearer Auth |
| `POST` | `/v1/stories/{story_id}/feedback` | Submit star rating, touch score, and resonance tags | Bearer Auth |

### 🌿 Liberation Journeys (Premium Curriculum)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/liberation/catalog` | Browse approved liberation journeys storefront | Bearer Auth |
| `GET` | `/v1/liberation/catalog/{code}` | Get specific liberation definition and day blueprints | Bearer Auth |
| `GET` | `/v1/liberation/my-journeys` | List user's purchased transformation journeys | Bearer Auth |
| `POST` | `/v1/liberation/{code}/enroll` | Enroll in journey progress post-purchase | Bearer Auth |
| `POST` | `/v1/liberation/{code}/repeat` | Restart / reset a completed journey | Bearer Auth |
| `GET` | `/v1/liberation/{code}/status` | Check day unlock and completion status | Bearer Auth |
| `POST` | `/v1/liberation/{code}/day/{day}/generate` | Submit morning feeling and receive daily exercise | Bearer Auth |
| `POST` | `/v1/liberation/{code}/day/{day}/complete` | Submit post-exercise reflection and unlock next day | Bearer Auth |
| `GET` | `/v1/liberation/{code}/day/{day}` | Review completed day reflections and exercise | Bearer Auth |
| `GET` | `/v1/liberation/feed-card` | Get journey promotional or progress card for feed | Bearer Auth / Guest |

### 💳 Payments & Subscriptions
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/v1/payment/checkout/start` | Create Stripe checkout session for plan or journey | Bearer Auth |
| `POST` | `/v1/payment/webhook` | Process Stripe subscription and checkout webhooks | Stripe Secret |
| `GET` | `/v1/payment/history/{user_id}` | Retrieve payment and billing invoices | Bearer Auth |
| `GET` | `/v1/subscription/plans` | List active subscription tiers | Public |
| `GET` | `/v1/subscription/status` | Check current user subscription tier and status | Bearer Auth |
| `POST` | `/v1/subscription/cancel` | Cancel an active recurring subscription | Bearer Auth |

### 🛡️ Admin Moderation & Control Center (`/v1/admin`)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/admin/dashboard/stats` | High-level platform statistics and KPIs | Admin Only |
| `GET` | `/v1/admin/dashboard/figma-stats` | Aggregated metrics formatted for admin UI | Admin Only |
| `POST` | `/v1/admin/chat` | AI-powered natural language database query assistant | Admin Only |
| `GET` | `/v1/admin/moderation/queue` | Paginated queue of pending story publications | Admin Only |
| `GET` | `/v1/admin/moderation/story/{id}` | Inspect story detail for moderation review | Admin Only |
| `PUT` | `/v1/admin/moderation/story/{id}` | Edit story copy, titles, or tags during review | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/approve-content` | Approve written text independently | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/approve-cover` | Approve cover artwork independently | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/approve-voice` | Approve narration audio independently | Admin Only |
| `PATCH` | `/v1/admin/moderation/story/{id}/voice-requirement` | Toggle whether voice is strictly required | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/regenerate-cover` | Queue AI cover regeneration for moderation | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/cover` | Upload manual cover replacement to S3 | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/audio` | Upload manual audio replacement | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/publish` | Publish story to global feed once approved | Admin Only |
| `POST` | `/v1/admin/moderation/story/{id}/reject` | Reject submission with review notes | Admin Only |
| `DELETE` | `/v1/admin/moderation/story/{id}` | Permanently delete submission from queue | Admin Only |
| `GET` | `/v1/admin/photos` | List photo cover image assets in S3 | Admin Only |
| `POST` | `/v1/admin/photos` | Upload new cover asset to AWS S3 | Admin Only |
| `PATCH` | `/v1/admin/photos/{id}` | Update photo metadata or active status | Admin Only |
| `DELETE` | `/v1/admin/photos/{id}` | Delete photo record and purge S3 object | Admin Only |
| `GET` | `/v1/admin/voice-review` | Voice narration moderation review queue | Admin Only |
| `POST` | `/v1/admin/voice-review/{id}/regenerate` | Trigger instant re-narration of story | Admin Only |
| `GET` | `/v1/admin/users` | List platform users with search and filters | Admin Only |
| `GET` | `/v1/admin/users/{id}` | View detailed user account & subscription record | Admin Only |
| `PATCH` | `/v1/admin/users/{id}` | Update user role or account status | Admin Only |
| `DELETE` | `/v1/admin/users/{id}` | Soft-delete / deactivate user account | Admin Only |
| `GET` | `/v1/admin/billing/stats` | View financial MRR and subscription telemetry | Admin Only |
| `GET` | `/v1/admin/billing/subscriptions`| List active subscriber accounts | Admin Only |

### 🧪 Non-Production Test & Preview Endpoints
> *Automatically disabled when `APP_ENV=production`.*

| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET/POST` | `/v1/test/cover-template-preview` | Live 2160×2160 PNG render of HTML/CSS cover template via Playwright | Non-Prod |
| `GET` | `/v1/test/confession-cover-style-preview` | Live DALL-E confession style generation and prompt inspector | Non-Prod |

---

## 📄 License
This repository is proprietary software belonging to **Transform to Liberation**. Unauthorized copying, distribution, or deployment is strictly prohibited.
