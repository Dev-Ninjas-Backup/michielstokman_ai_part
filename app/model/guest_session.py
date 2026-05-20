import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base


class GuestSession(Base):
    """Tracks anonymous guest sessions and enforces one-story-per-day limits."""
    __tablename__ = "guest_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The date the guest last accessed a full story detail page
    last_story_date = Column(Date, nullable=True)

    # The story_id the guest read on that date (for auditing)
    last_story_id = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
