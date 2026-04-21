"""
app/model/cover_image.py

Database model for admin-managed story cover images.
Images are stored on AWS S3 — the image_url column holds the full S3 URL.

Admins upload cover images per story type (confession, meditation, transformation).
A story references its cover via stories.cover_image_url (denormalised S3 URL).
"""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class CoverImageType(str, enum.Enum):
    confession = "confession"
    meditation = "meditation"
    transformation = "transformation"


class CoverImage(Base):
    __tablename__ = "cover_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Story type this image belongs to
    story_type = Column(
        SAEnum(CoverImageType),
        nullable=False,
        index=True,
    )

    # Full AWS S3 URL — e.g. https://bucket.s3.region.amazonaws.com/images/abc.jpg
    image_url = Column(String, nullable=False)

    # S3 object key stored separately to allow deletion from S3 later
    # e.g. "images/abc123.jpg"
    s3_key = Column(String, nullable=False)

    # Admin can deactivate without deleting
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Who uploaded it
    uploaded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
    uploader = relationship("User", foreign_keys=[uploaded_by])
