import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1.endpoints import hello
from app.api.v1.endpoints import routes_ai, routes_auth, routes_payment, routes_subscription, routes_profile
from app.api.v1.endpoints import routes_user_dashboard, routes_feedback, routes_liberation, routes_liberation_catalog
from app.api.v1.endpoints.admin import route_admin_dashboard, route_moderation, route_liberation_admin
from app.schemas.schema_system import HealthResponse

app = FastAPI(
    title="Transform to Liberation API",
    description="SuperGrok-powered personalised story generation with ElevenLabs TTS.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(routes_profile.router, prefix="/v1", tags=["Profile"])

# User dashboard routes
app.include_router(routes_user_dashboard.router, prefix="/v1", tags=["User Dashboard"])
app.include_router(routes_feedback.router, prefix="/v1", tags=["Feedback"])
app.include_router(routes_liberation.router, prefix="/v1", tags=["Liberation Journey"])
app.include_router(routes_liberation_catalog.router, prefix="/v1", tags=["Liberation Catalog"])

# Admin routes
app.include_router(route_admin_dashboard.router, prefix="/v1", tags=["Admin"])
app.include_router(route_moderation.router, prefix="/v1", tags=["Admin - Moderation"])
app.include_router(route_liberation_admin.router, prefix="/v1", tags=["Admin - Liberation"])

# ---------------------------------------------------------------------------
# System / Infrastructure Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """
    Verifies that the API is alive. Used by AWS Load Balancers or Uptime monitors.
    """
    return {
        "status": "online",
        "message": "Transform to Liberation Backend is up and running.",
        "version": "1.0.0"
    }
