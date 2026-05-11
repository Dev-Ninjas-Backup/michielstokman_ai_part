import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum, Boolean, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.db import Base
import enum


class StoryType(str, enum.Enum):
    confession = "confession"
    meditation = "meditation"
    transformation = "transformation"


class GenerationStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ModerationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    flagged = "flagged"


class Story(Base):
    __tablename__ = "stories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content
    story_type = Column(SAEnum(StoryType), nullable=False)
    title = Column(String, nullable=True)
    story_text = Column(Text, nullable=True)

    # Audio — S3 URL (falls back to local path e.g. "media/audio/abc123.mp3" if S3 not configured)
    audio_path = Column(String, nullable=True)

    # Cover image — full S3 URL assigned by admin via Photo Management
    # e.g. "https://bucket.s3.region.amazonaws.com/images/abc123.jpg"
    cover_image_url = Column(String, nullable=True)

    # Associated track from the music library
    track_id = Column(String, nullable=True)

    # Snapshot of the user's profile context at generation time
    country_city = Column(String, nullable=True)
    life_phase = Column(String, nullable=True)
    relationship_status = Column(String, nullable=True)
    deepest_desire_fear = Column(String, nullable=True)
    specific_trigger = Column(String, nullable=True)
    emotional_context = Column(JSONB, nullable=True)   # slider values dict
    high_intensity = Column(Boolean, default=False, nullable=False)

    # Figma Dashboard Metrics
    views_count = Column(Integer, default=0, nullable=False)
    shares_count = Column(Integer, default=0, nullable=False)
    pulse_score = Column(Float, default=0.0, nullable=False)
    reflections_count = Column(Integer, default=0, nullable=False)

    # Ownership:
    # - user_id is set when a USER generates their own story
    # - admin_id is set when an ADMIN creates a bulk / template story
    # Only one of these will be non-null per row.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    admin_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Async job tracking
    job_id = Column(String, nullable=True, index=True)
    generation_status = Column(
        SAEnum(GenerationStatus),
        nullable=False,
        default=GenerationStatus.processing,
    )

    # Moderation tracking
    moderation_status = Column(
        SAEnum(ModerationStatus),
        nullable=False,
        default=ModerationStatus.pending,
        index=True,
    )
    moderation_notes = Column(String, nullable=True)
    moderation_reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    moderation_reviewed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="stories_as_user")
    admin = relationship("User", foreign_keys=[admin_id], backref="stories_as_admin")
    moderator = relationship("User", foreign_keys=[moderation_reviewed_by], backref="moderated_stories")
