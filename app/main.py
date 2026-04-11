import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.v1.endpoints import hello
from app.api.v1.endpoints import routes_ai, routes_auth, routes_payment, routes_subscription

app = FastAPI(
    title="Transform to Liberation API",
    description="SuperGrok-powered personalised story generation with ElevenLabs TTS.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Static files — Audio storage
# ⚠️  S3 MIGRATION NOTE: When S3 is ready, remove this mount and serve audio
#     directly from S3 URLs. The audio_path column in the stories table will
#     then hold the full S3 URL instead of the local relative path.
# ---------------------------------------------------------------------------
AUDIO_DIR = "media/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
app.mount("/media/audio", StaticFiles(directory=AUDIO_DIR), name="audio")

app.include_router(hello.router, prefix="/v1")
app.include_router(routes_ai.router, prefix="/v1", tags=["AI"])
app.include_router(routes_auth.router, prefix="/v1",tags=["Auth"])
app.include_router(routes_payment.router, prefix="/v1", tags=["Payment"])
app.include_router(routes_subscription.router, prefix="/v1", tags=["Subscription"])


