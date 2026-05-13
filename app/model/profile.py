import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.db import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # Step 1: Demographics
    true_name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    height = Column(String, nullable=True)
    education = Column(String, nullable=True)
    annual_income = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    sexual_orientation = Column(String, nullable=True)

    # Step 2: Life Phase & Bio
    life_phase = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)  # Avatar image URL

    # Step 3: Priorities (Slider values, e.g., 0-5 or 0-10)
    slider_desire_relationship = Column(Float, nullable=True)
    slider_life_purpose = Column(Float, nullable=True)
    slider_career_money = Column(Float, nullable=True)
    slider_true_self = Column(Float, nullable=True)
    slider_sexuality_life_energy = Column(Float, nullable=True)
    slider_fear_freedom = Column(Float, nullable=True)
    slider_health_body = Column(Float, nullable=True)
    slider_enlightenment = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship back to User
    user = relationship("User", back_populates="profile")
