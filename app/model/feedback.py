"""
app/model/feedback.py
Database model for storing user feedback/reviews on stories.
Captures the full Resonance Reflection form: touch score, star rating,
resonance tags, reaction, and free-text feedback.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import backref, relationship
from app.core.db import Base


class StoryFeedback(Base):
    __tablename__ = "story_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Which story and which user
    story_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Slider: "How much did this touch or open something in you right now?" (0-10)
    touch_score = Column(Float, nullable=True)

    # Star rating (e.g. 4.3 out of 5)
    star_rating = Column(Float, nullable=True)

    # Tags that resonated (e.g. ["Voice", "Emotional Arc", "Liberation Moment"])
    resonance_tags = Column(ARRAY(String), nullable=True)

    # Quick reaction pill (e.g. "Love this", "More like this", "Too Intense", "Not my vibe")
    reaction = Column(String, nullable=True)

    # Free-form text ("Share a thought...")
    feedback_text = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    # DB already has ON DELETE CASCADE. Without passive_deletes, SQLAlchemy loads
    # feedback_entries on story delete and tries to NULL story_id — which 500s
    # because the column is NOT NULL (admin DELETE /v1/admin/moderation/story/{id}).
    story = relationship(
        "Story",
        backref=backref(
            "feedback_entries",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )
    user = relationship("User", backref="story_feedback")

    # One feedback per user per story
    __table_args__ = (
        UniqueConstraint("story_id", "user_id", name="uq_story_user_feedback"),
    )
