from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, content, credits, health, liberations, profile, stories, submissions
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.models.entities import ContentItem, ContentType, LiberationPlan


def seed_data() -> None:
    db = SessionLocal()
    try:
        has_content = db.query(ContentItem).first() is not None
        if not has_content:
            db.add_all(
                [
                    ContentItem(
                        content_type=ContentType.confession,
                        title="The Morning I Stopped Running",
                        subtitle="A story about slowing down and finally feeling",
                        body="A raw confession that meets fear with tenderness.",
                        rating=4.3,
                        duration_sec=767,
                        tags=["self-discovery", "fear-freedom"],
                    ),
                    ContentItem(
                        content_type=ContentType.meditation,
                        title="The Morning I Stopped Running",
                        subtitle="Gentle guided reset in under 13 minutes",
                        body="Breath, posture, and emotional grounding.",
                        rating=4.2,
                        duration_sec=720,
                        tags=["inner-peace", "reset"],
                    ),
                    ContentItem(
                        content_type=ContentType.journey,
                        title="Feel More Vital - 7 Days to More Life Energy",
                        subtitle="A seven day liberation for body and mind",
                        body="Daily rituals and reflections to rebuild vitality.",
                        rating=4.3,
                        duration_sec=0,
                        price_cents=4700,
                        tags=["vitality", "7-day"],
                    ),
                ]
            )

        has_plan = db.query(LiberationPlan).first() is not None
        if not has_plan:
            db.add(
                LiberationPlan(
                    title="Feel More Vital",
                    description="Seven days of gentle daily practices to recover your natural vitality.",
                    price_cents=4700,
                    days_count=7,
                    is_active=True,
                )
            )

        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_data()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(profile.router, prefix=settings.api_prefix)
app.include_router(content.router, prefix=settings.api_prefix)
app.include_router(credits.router, prefix=settings.api_prefix)
app.include_router(stories.router, prefix=settings.api_prefix)
app.include_router(submissions.router, prefix=settings.api_prefix)
app.include_router(liberations.router, prefix=settings.api_prefix)
