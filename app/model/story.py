import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum, Boolean, Float, Integer, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.db import Base
import enum

# Postgres sequence backing the human-readable story number. Created in the
# migration rather than by SQLAlchemy so existing rows can be backfilled first.
STORY_NUMBER_SEQUENCE = "story_number_seq"


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


class SubmissionStatus(str, enum.Enum):
    """Member-controlled lifecycle, independent of admin moderation."""
    draft = "draft"
    submitted = "submitted"
    withdrawn = "withdrawn"


class ImageSource(str, enum.Enum):
    """Where the cover image on a story came from."""
    ai_generated = "ai_generated"
    user_uploaded = "user_uploaded"
    admin_default = "admin_default"


class SubmissionMode(str, enum.Enum):
    """How the member submitted the piece."""
    studio = "studio"
    human_ready = "human_ready"


class AssetReviewStatus(str, enum.Enum):
    """Per-asset publication review state (content, cover, voice)."""
    missing = "missing"
    pending = "pending"
    in_progress = "in_progress"
    ready_for_review = "ready_for_review"
    approved = "approved"
    rejected = "rejected"


ASSET_REVIEW_STATUS = SAEnum(AssetReviewStatus, name="assetreviewstatus")


class Story(Base):
    __tablename__ = "stories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Short, human-readable identifier shown to members (e.g. "TTL-000042").
    # Allocated by a Postgres sequence so numbers are stable and never reused.
    story_number = Column(
        Integer,
        server_default=text(f"nextval('{STORY_NUMBER_SEQUENCE}')"),
        unique=True,
        index=True,
        nullable=True,
    )

    # Content
    story_type = Column(SAEnum(StoryType), nullable=False)
    title = Column(String, nullable=True)
    member_title = Column(
        String,
        nullable=True,
        comment="Title the member submitted on create or edit",
    )
    ai_generated_title = Column(
        String,
        nullable=True,
        comment="Title produced by the LLM TITLE: line",
    )
    use_ai_title = Column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="When true, the active title prefers ai_generated_title",
    )
    story_text = Column(Text, nullable=True)

    # Audio — S3 URL (falls back to local path e.g. "media/audio/abc123.mp3" if S3 not configured)
    audio_path = Column(String, nullable=True)
    voice_name = Column(String, nullable=True)
    # Raw provider voice identifier. Set for cloned member voices, which have no
    # entry in the predefined catalog and so cannot be resolved from voice_name.
    voice_id = Column(String, nullable=True)
    uses_custom_voice = Column(Boolean, default=False, nullable=False)
    audio_duration_seconds = Column(Integer, nullable=True)
    alignment = Column(JSONB, nullable=True)

    # Cover image — full S3 URL assigned by admin via Photo Management
    # e.g. "https://bucket.s3.region.amazonaws.com/images/abc123.jpg"
    cover_image_url = Column(String, nullable=True)
    # Storage key for the cover, needed to clean up the object when it is replaced.
    cover_image_key = Column(String, nullable=True)
    image_source = Column(SAEnum(ImageSource), nullable=True)

    # Teaser/intro copy generated per distribution platform.
    # Shape: {"instagram": str, "facebook": str, "spotify": str}
    social_intros = Column(JSONB, nullable=True)
    social_intros_generated_at = Column(DateTime, nullable=True)

    # Associated track from the music library
    track_id = Column(String, nullable=True)

    # Snapshot of the user's profile context at generation time
    # Figma Inputs
    first_name = Column(String, nullable=True)
    location = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    sexual_orientation = Column(String, nullable=True)
    occupation = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    background = Column(Text, nullable=True)
    personality = Column(Text, nullable=True)
    lifestyle = Column(Text, nullable=True)
    situation = Column(Text, nullable=True)
    story_input = Column(Text, nullable=True)
    submission_mode = Column(
        SAEnum(SubmissionMode, name="submissionmode"),
        nullable=False,
        default=SubmissionMode.studio,
        server_default=SubmissionMode.studio.value,
    )
    growth_areas = Column(JSONB, nullable=True) # list of strings
    life_phase = Column(String, nullable=True)
    tags = Column(JSONB, nullable=True)         # list of strings
    high_intensity = Column(Boolean, default=False, nullable=False)
    # Juicy 2–4 sentence excerpt for the public details hero and listing cards.
    hero_hook = Column(Text, nullable=True)
    # Short brush-stroke line for the details hero (title is the display fallback).
    hero_tagline = Column(Text, nullable=True)
    # Admin-only editorial note from the moderation desk. Never public.
    editorial_brief = Column(Text, nullable=True)

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

    # Member-controlled submission lifecycle. Withdrawn stories stay in the
    # member's library but are excluded from public feeds and moderation queues.
    submission_status = Column(
        SAEnum(SubmissionStatus),
        nullable=False,
        default=SubmissionStatus.submitted,
        server_default=SubmissionStatus.submitted.value,
        index=True,
    )
    withdrawn_at = Column(DateTime, nullable=True)
    # Number of times the member has edited the text and re-run the AI pipeline.
    regeneration_count = Column(Integer, default=0, nullable=False, server_default="0")

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

    content_status = Column(
        ASSET_REVIEW_STATUS,
        nullable=False,
        default=AssetReviewStatus.pending,
        server_default="pending",
    )
    cover_status = Column(
        ASSET_REVIEW_STATUS,
        nullable=False,
        default=AssetReviewStatus.missing,
        server_default="missing",
    )
    voice_status = Column(
        ASSET_REVIEW_STATUS,
        nullable=False,
        default=AssetReviewStatus.missing,
        server_default="missing",
    )
    voice_not_required = Column(Boolean, default=False, nullable=False, server_default="false")
    published_at = Column(DateTime, nullable=True)

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
