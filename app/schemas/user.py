from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, UUID4, ConfigDict

# Shared properties
class UserBase(BaseModel):
    email: EmailStr

# Properties to receive via API on creation (Signup)
class UserCreate(UserBase):
    password: str

# Properties to receive via API on login
class UserLogin(UserBase):
    password: str

# Properties to receive via API for social login (Google/Apple)
class SocialLoginRequest(BaseModel):
    provider: str  # "google" or "apple"
    token: str     # The id_token or JWT from the provider

# Properties to return via API (Response)
class UserResponse(UserBase):
    id: UUID4
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

# JSON payload containing the JWT token
class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    is_new_user: bool = False
