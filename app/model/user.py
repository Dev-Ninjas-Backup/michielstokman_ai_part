import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.db import Base

class User(Base):
    __tablename__ = "users"

    # Native UUID type for PostgreSQL
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    
    # Nullable because OAuth-only users might not have a password initially
    password_hash = Column(String, nullable=True) 
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    token_version = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime, nullable=True)

    # Relationship to handle OAuth accounts (Option 2 approach)
    oauth_accounts = relationship("UserOAuthAccount", back_populates="user", cascade="all, delete-orphan")


class UserOAuthAccount(Base):
    __tablename__ = "user_oauth_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)  # e.g., 'google', 'apple', 'github'
    provider_account_id = Column(String, nullable=False)  # e.g., the unique ID provided by Google
    
    # Relationship back to the User
    user = relationship("User", back_populates="oauth_accounts")

    # Ensure a given provider and provider_ID combination is totally unique globally
    __table_args__ = (
        UniqueConstraint('provider', 'provider_account_id', name='uq_provider_account'),
    )
