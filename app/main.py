# CI/CD Deployment Test
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.core.config import settings
from app.core.responses import register_exception_handlers
from app.api.v1.endpoints import hello
from app.api.v1.endpoints import routes_ai, routes_auth, routes_payment, routes_subscription, routes_profile
from app.api.v1.endpoints import routes_user_dashboard, routes_feedback, routes_liberation, routes_liberation_catalog
from app.api.v1.endpoints import routes_my_stories
from app.api.v1.endpoints import routes_cover_template_test
from app.api.v1.endpoints import routes_confession_cover_style_test
from app.api.v1.endpoints.admin import route_admin_dashboard, route_moderation, route_liberation_admin, route_admin_chat, route_photo_management, route_voice_review, route_billing_admin, route_admin_users
from app.schemas.schema_system import HealthResponse

app = FastAPI(
    title="Transform to Liberation API",
    description="SuperGrok-powered personalised story generation with ElevenLabs TTS.",
    version="1.0.1",
)

# ---------------------------------------------------------------------------
# Customize OpenAPI Schema to support pasting arbitrary JWT / Bearer tokens directly
# ---------------------------------------------------------------------------
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Ensure security schemes structure is initialized
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
        
    # Standard OAuth2 Password flow scheme
    openapi_schema["components"]["securitySchemes"]["OAuth2PasswordBearer"] = {
        "type": "oauth2",
        "flows": {
            "password": {
                "tokenUrl": "/v1/login",
                "scopes": {}
            }
        }
    }
    
    # New HTTP Bearer scheme allowing pasting standard JWT tokens directly
    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your Bearer token directly here (e.g. your guest access token)."
    }
    
    # Apply both security requirements to any route that uses authorization
    for route in openapi_schema["paths"].values():
        for method in route.values():
            if "security" in method:
                # Add BearerAuth as an alternative to whatever OAuth2 scheme exists
                if not any("BearerAuth" in req for req in method["security"]):
                    method["security"].append({"BearerAuth": []})
            else:
                method["security"] = [{"OAuth2PasswordBearer": []}, {"BearerAuth": []}]
                
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# ---------------------------------------------------------------------------
# Static files — Audio and Image storage
# ⚠️  S3 MIGRATION NOTE: When S3 is ready, remove these mounts and serve files
#     directly from S3 URLs. The path columns in the tables will
#     then hold the full S3 URL instead of the local relative path.
# ---------------------------------------------------------------------------
AUDIO_DIR = "media/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
app.mount("/media/audio", StaticFiles(directory=AUDIO_DIR), name="audio")

IMAGE_DIR = "media/images"
os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/media/images", StaticFiles(directory=IMAGE_DIR), name="images")


app.include_router(hello.router, prefix="/v1")
app.include_router(routes_ai.router, prefix="/v1", tags=["AI"])
app.include_router(routes_auth.router, prefix="/v1",tags=["Auth"])
app.include_router(routes_payment.router, prefix="/v1", tags=["Payment"])
app.include_router(routes_subscription.router, prefix="/v1", tags=["Subscription"])
app.include_router(routes_profile.router, prefix="/v1", tags=["Profile"])

# User dashboard routes
app.include_router(routes_user_dashboard.router, prefix="/v1", tags=["User Dashboard"])
app.include_router(routes_feedback.router, prefix="/v1", tags=["Feedback"])
app.include_router(routes_my_stories.router, prefix="/v1")
app.include_router(routes_liberation.router, prefix="/v1")
app.include_router(routes_liberation_catalog.router, prefix="/v1")

# Admin routes
app.include_router(route_admin_dashboard.router, prefix="/v1", tags=["Admin"])
app.include_router(route_moderation.router, prefix="/v1", tags=["Admin - Moderation"])
app.include_router(route_liberation_admin.router, prefix="/v1")
app.include_router(route_admin_chat.router, prefix="/v1", tags=["Admin - Metrics Chat"])
app.include_router(route_photo_management.router, prefix="/v1", tags=["Admin - Photo Management"])
app.include_router(route_voice_review.router, prefix="/v1", tags=["Admin - Voice Review"])
app.include_router(route_billing_admin.router, prefix="/v1", tags=["Admin - Billing"])
app.include_router(route_admin_users.router, prefix="/v1", tags=["Admin - Users"])
app.include_router(
    routes_cover_template_test.router,
    prefix="/v1",
    tags=["Test - Cover Template"],
)
app.include_router(
    routes_confession_cover_style_test.router,
    prefix="/v1",
    tags=["Test - Confession Cover Style"],
)

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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transform to Liberation - Backend API</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0b0e14;
            color: #f3f4f6;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
            overflow: hidden;
            position: relative;
        }
        .glow {
            position: absolute;
            width: 400px;
            height: 400px;
            background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, rgba(99, 102, 241, 0) 70%);
            top: -100px;
            left: -100px;
            z-index: 1;
        }
        .glow-alt {
            position: absolute;
            width: 400px;
            height: 400px;
            background: radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, rgba(168, 85, 247, 0) 70%);
            bottom: -100px;
            right: -100px;
            z-index: 1;
        }
        .card {
            background-color: #121620;
            border: 1px solid #1e2536;
            border-radius: 16px;
            padding: 40px;
            width: 100%;
            max-width: 540px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4);
            z-index: 10;
            position: relative;
            backdrop-filter: blur(10px);
        }
        .title {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 8px;
            color: #ffffff;
            letter-spacing: -0.025em;
        }
        .subtitle {
            font-size: 14px;
            color: #9ca3af;
            line-height: 1.6;
            margin-bottom: 24px;
            font-weight: 300;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            background-color: #1e2536;
            color: #9ca3af;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 28px;
            border: 1px solid #2a344a;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 28px;
        }
        .grid-item {
            background-color: #161c28;
            border: 1px solid #222b3d;
            border-radius: 10px;
            padding: 16px;
        }
        .label {
            font-size: 10px;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }
        .value {
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
        }
        .status-container {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .dot {
            width: 8px;
            height: 8px;
            background-color: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 10px #10b981;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            }
            70% {
                transform: scale(1);
                box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
            }
            100% {
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
            }
        }
        .button {
            display: flex;
            align-items: center;
            width: 100%;
            background-color: #161c28;
            border: 1px solid #222b3d;
            border-radius: 10px;
            padding: 16px 20px;
            color: #ffffff;
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
            margin-bottom: 12px;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        .button:hover {
            background-color: #1c2434;
            border-color: #3b82f6;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
        }
        .button-icon {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            background-color: rgba(59, 130, 246, 0.1);
            color: #3b82f6;
            border-radius: 6px;
            margin-right: 14px;
        }
        .button-icon-alt {
            background-color: rgba(239, 68, 68, 0.1);
            color: #ef4444;
        }
        .footer {
            text-align: center;
            font-size: 11px;
            color: #4b5563;
            margin-top: 32px;
        }
    </style>
</head>
<body>
    <div class="glow"></div>
    <div class="glow-alt"></div>
    <div class="card">
        <h1 class="title">transform_to_liberation_server</h1>
        <p class="subtitle">Backend API for Transform to Liberation — a full featured platform with personalized story generation, user management, Stripe payments, and ElevenLabs real-time audio synchronization.</p>
        
        <div class="badge">Backend Service</div>
        
        <div class="grid">
            <div class="grid-item">
                <div class="label">Release Version</div>
                <div class="value">v1.0.1</div>
            </div>
            <div class="grid-item">
                <div class="label">Deployment Version</div>
                <div class="value">20260519T171908</div>
            </div>
            <div class="grid-item">
                <div class="label">Environment</div>
                <div class="value">production</div>
            </div>
            <div class="grid-item">
                <div class="label">Status</div>
                <div class="status-container">
                    <div class="dot"></div>
                    <div class="value">Online</div>
                </div>
            </div>
        </div>

        <a href="/docs" class="button">
            <span class="button-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"></path><path d="M6 6h10"></path><path d="M6 10h10"></path></svg>
            </span>
            API Documentation
        </a>

        <a href="/health" class="button">
            <span class="button-icon button-icon-alt">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"></path></svg>
            </span>
            Health Check
        </a>

        <div class="footer">
            &copy; 2026 Transform to Liberation. All rights reserved.
        </div>
    </div>
</body>
</html>"""



#check in stuff