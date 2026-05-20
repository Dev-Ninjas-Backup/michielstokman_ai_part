# 🌿 Transform to Liberation API

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)
[![Postgres](https://img.shields.io/badge/Postgres-SQLAlchemy-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker)](https://www.docker.com/)
[![AWS S3](https://img.shields.io/badge/AWS-S3-569A31?style=for-the-badge&logo=amazons3)](https://aws.amazon.com/s3/)
[![Stripe](https://img.shields.io/badge/Stripe-Payments-008CFF?style=for-the-badge&logo=stripe)](https://stripe.com/)

A premium, production-grade, AI-driven backend powering **Transform to Liberation**—a transformative system built to generate personalized healing exercises, therapeutic stories, meditations, and semantic book recommendations based on user emotional input.

* **Production URL**: [https://www.transformtoliberation.com/](https://www.transformtoliberation.com/)
* **Interactive API Reference**: [https://www.transformtoliberation.com/docs](https://www.transformtoliberation.com/docs)

---

## 🏗️ Architecture & Server Routing

The system is deployed on an AWS EC2 instance reverse-proxied with **Nginx** and secured using SSL/TLS via **Let's Encrypt Certbot**.

```
                       [ HTTPS Traffic ]
                              │
                      [ Nginx (Port 443) ]
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   [ Next.js Frontend ]                [ FastAPI Backend ]
       Local Port 3000                  Local Port 8000
    (Home, UI, Pages)             (/v1/, /docs, /openapi.json)
```

### Nginx Routing Strategy
* **Frontend**: Dynamic UI routing handled by the Next.js service on port `3000`.
* **API Endpoints**: Gated behind the version-controlled `/v1/` prefix and routed natively to the FastAPI backend service on port `8000`.
* **Interactive Swagger Documentation**: Exposed under `/docs` for instantaneous schema inspection and developer sandboxing.

---

## ⚡ Tech Stack & Core Libraries

* **Core Framework**: [FastAPI](https://fastapi.tiangolo.com/) — high-performance, asynchronous REST framework.
* **Package & Env Manager**: [Astral `uv`](https://github.com/astral-sh/uv) — ultra-fast Python package resolution and virtual environment tool.
* **Database & ORM**: PostgreSQL, mapped asynchronously via [SQLAlchemy ORM](https://www.sqlalchemy.org/).
* **Vector Search Database**: [Pinecone](https://www.pinecone.io/) — real-time high-dimensional embedding indexes.
* **Large Language Models**: Grok & OpenAI integrations via langchain-compatible components.
* **Cloud Storage**: Amazon S3 for dynamic cover image uploads and generated voice audio file storage.
* **Subscriptions & Billing**: [Stripe](https://stripe.com/) — webhooks, secure checkout sessions, and premium subscription tracking.

---

## 🌟 Key Backend Components

### 1. The Story Generation Engine
A sophisticated asynchronous pipeline that takes user input (e.g. morning feelings, life context), queries relevant therapeutic metadata, and coordinates with an LLM generator. It then routes the generated script to a text-to-speech engine to generate a high-quality audio file, uploads it to S3, and saves it to the database for curation.

### 2. 7-Day Premium Liberation Journey
A progressive therapeutic workflow containing gated purchase validation and multi-day unlocks. The user submits check-ins, receives custom exercises daily, completes them by submitting post-exercise reflections, and increments their progress.

### 3. Personalized RAG Recommendations
An advanced Retrieval-Augmented Generation system. It fetches semantic user interaction patterns from database logs, runs similarity searches against embedded vectors in Pinecone, and synthesizes tailored book suggestions with detailed explanations using an LLM.

### 4. Admin Cover Image & Voice Management
* **Photo Cover System**: Dynamic uploading, editing, S3 object management, and categorization (`confession`, `meditation`, `journey`).
* **Voice Review Moderator**: Custom moderation queues for generated audio elements before publication to the global feed.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure you have the following installed on your machine:
* Python 3.11+
* Docker & Docker Compose
* PostgreSQL (if running bare metal)

### 2. Installation using Astral `uv`
The project leverages `uv` for blisteringly fast dependency management:

```bash
# Clone the repository
git clone https://github.com/TashinMahmud/TransformToLiberation.git
cd TransformToLiberation

# Install uv (if not already installed)
pip install uv

# Initialize virtual environment and sync dependencies
uv venv
uv sync
```

### 3. Running Locally
Make sure you copy the `.env.example` into a local `.env` and fill out your S3, Pinecone, and Stripe secrets.

**Development server:**
```bash
# Activate the virtual environment
.venv\Scripts\activate   # On Windows
source .venv/bin/activate # On Unix/macOS

# Run development server with auto-reload
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Docker Compose setup:**
```bash
docker compose up --build -d
```

---

## 🧭 Complete API Endpoint Reference

### 🔐 System & Authentication
* `GET /health` — Simple service heartbeat check.
* `POST /v1/signup` — Register a new account.
* `POST /v1/login` — Login to receive a JWT access token.
* `POST /v1/signout` — Invalidate current token and sign out safely.

### 👤 Profile & User Data
* `GET /v1/me/profile` — Fetch the profile of the current user.
* `PUT /v1/me/profile` — Create or update user name, age, and country profiles.

### 🔮 AI & Generation Endpoints
* `POST /v1/ai/story/generate` — Start a background thread for dynamic audio story creation.
* `GET /v1/admin/ai/status/{job_id}` — Poll execution status of the generation job.
* `GET /v1/ai/search` — Perform a semantic search on generated tracks.
* `POST /v1/ai/rag/ingest/all` — Admin trigger to run database embedding generation and ingestion.

### 📊 Dashboard & Feeds
* `GET /v1/dashboard/feed` — Discovery grid feed combining standard stories and Liberation Journey cards.
* `GET /v1/stories/{story_id}` — High-performance detail player page view with rating/resonance telemetry.
* `GET /v1/dashboard/recommendations` — Fetch Grok + Pinecone RAG book recommendations.
* `GET /v1/dashboard/credits` — Query remaining/limit details for user daily credits.

### 🌿 Liberation Journey (Premium)
* `POST /v1/liberation/{journey_code}/enroll` — Unlock journey progress.
* `GET /v1/liberation/{journey_code}/status` — Status tracker displaying unlocked/locked days.
* `GET /v1/liberation/my-journeys` — User personal library containing purchased transformation paths.
* `POST /v1/liberation/{journey_code}/day/{day}/generate` — Save morning feelings and download daily exercise.
* `POST /v1/liberation/{journey_code}/day/{day}/complete` — Record post-exercise reflections and open next day.

### 📸 Photo Cover Image Management (Admin)
* `POST /v1/admin/photos` — Upload and publish a new cover image to AWS S3.
* `GET /v1/admin/photos` — Fetch cover image directories (Supports singular lowercase filtering).
* `PATCH /v1/admin/photos/{id}` — Update metadata or completely swap active image.
* `DELETE /v1/admin/photos/{id}` — Purge DB record and remove raw object from AWS S3 bucket.

### 🎙️ Voice Moderation
* `GET /v1/admin/voice-review` — Retrieve the voice moderation list (Supports `All`, `Stories`, `Meditations` filtering).
