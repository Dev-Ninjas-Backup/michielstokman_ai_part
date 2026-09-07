"""Admin user management schemas."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.schema_system import PaginationMeta


class AdminUserListItem(BaseModel):
    id: UUID
    email: EmailStr
    display_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    is_verified: bool
    story_count: int = 0
    created_at: datetime
    last_login: Optional[datetime] = None


class AdminUserListResponse(BaseModel):
    users: List[AdminUserListItem]
    meta: PaginationMeta


class AdminUserProfileSummary(BaseModel):
    true_name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    gender: Optional[str] = None
    profile_image_url: Optional[str] = None


class AdminUserDetail(BaseModel):
    id: UUID
    email: EmailStr
    display_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    is_verified: bool
    is_profile_setup: bool
    token_version: int
    created_at: datetime
    last_login: Optional[datetime] = None
    story_count: int = 0
    profile: Optional[AdminUserProfileSummary] = None
    credits_remaining: Optional[int] = None
    has_active_subscription: bool = False


class AdminUserPatchRequest(BaseModel):
    is_active: Optional[bool] = Field(
        None, description="False bans the account; True unbans."
    )
    is_admin: Optional[bool] = Field(
        None, description="Promote or demote admin privileges."
    )


class AdminUserDeleteResponse(BaseModel):
    user_id: UUID
    stories_deleted: int = 0
    message: str = "User deleted"
