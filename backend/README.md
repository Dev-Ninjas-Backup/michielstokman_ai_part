# Backend Service

Standalone FastAPI backend implementation for the Figma integration flow.
This folder is isolated and does not modify the existing application code.

## Features

- JWT auth (signup/login/me)
- Profile onboarding update/get
- Discover content listing
- Daily credits (get/consume)
- Story generation pipeline (queue + status + history)
- Story reflection save/get
- User submissions create/list
- Liberation plans, enrollment, day progression, completion

## Run

1. Create environment and install dependencies:

   `pip install -r requirements.txt`

2. Start server from this folder:

   `uvicorn app.main:app --reload`

3. Open docs:

   `http://127.0.0.1:8000/docs`

## Notes

- SQLite is used by default with `backend.db` in this folder.
- `POST /v1/liberations/start-checkout` is currently a mock paid flow.
- Story generation is deterministic placeholder text; replace with your LLM/TTS integration.
