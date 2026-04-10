from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileUpdate(BaseModel):
    true_name: str | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    country: str | None = None
    city: str | None = None
    region: str | None = None
    education: str | None = None
    annual_income: str | None = None
    gender: str | None = None
    sexual_orientation: str | None = None
    life_phase: str | None = None

    slider_desire_relationship: int | None = Field(default=None, ge=0, le=10)
    slider_life_purpose: int | None = Field(default=None, ge=0, le=10)
    slider_career_money: int | None = Field(default=None, ge=0, le=10)
    slider_true_self: int | None = Field(default=None, ge=0, le=10)
    slider_security_energy: int | None = Field(default=None, ge=0, le=10)
    slider_free_freedom: int | None = Field(default=None, ge=0, le=10)
    slider_health_body: int | None = Field(default=None, ge=0, le=10)
    slider_enlightenment: int | None = Field(default=None, ge=0, le=10)
    slider_social_relational: int | None = Field(default=None, ge=0, le=10)


class UserProfileResponse(UserProfileUpdate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreditWalletResponse(BaseModel):
    daily_limit: int
    remaining: int
    last_reset_date: date


class ConsumeCreditRequest(BaseModel):
    reason: str = "story_generation"


class ConsumeCreditResponse(BaseModel):
    consumed: bool
    remaining: int


class ContentCard(BaseModel):
    id: str
    content_type: Literal["confession", "meditation", "journey"]
    title: str
    subtitle: str
    body: str
    rating: float
    duration_sec: int
    price_cents: int | None = None
    tags: list[str]


class DiscoverResponse(BaseModel):
    items: list[ContentCard]


class StoryGenerateRequest(BaseModel):
    content_type: Literal["confession", "meditation", "journey"]
    track_id: str | None = None
    emotional_sliders: dict[str, int] | None = None
    life_phase: str | None = None
    specific_trigger: str | None = None
    high_intensity: bool = False


class StoryJobResponse(BaseModel):
    story_id: str
    job_id: str
    status: Literal["processing", "completed", "failed"]
    message: str


class StoryStatusResponse(BaseModel):
    story_id: str
    job_id: str
    status: Literal["processing", "completed", "failed"]
    story_text: str | None = None
    audio_path: str | None = None


class StoryItemResponse(BaseModel):
    id: str
    job_id: str
    content_type: Literal["confession", "meditation", "journey"]
    track_id: str | None = None
    status: Literal["processing", "completed", "failed"]
    story_text: str | None = None
    audio_path: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReflectionCreateRequest(BaseModel):
    resonance_score: float = Field(ge=0, le=10)
    moment_tags: list[str] = Field(default_factory=list)
    thought_note: str | None = None
    reaction: str | None = Field(default=None, max_length=50)


class ReflectionResponse(ReflectionCreateRequest):
    id: str
    story_id: str
    user_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionCreateRequest(BaseModel):
    content_type: Literal["confession", "meditation", "journey"]
    title: str = Field(min_length=3, max_length=255)
    first_name: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=10, max_length=5000)
    details: str | None = None
    growth_areas: list[str] = Field(default_factory=list)
    life_phase_tags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    contains_sensitive_content: bool = False


class SubmissionResponse(BaseModel):
    id: str
    user_id: str
    content_type: Literal["confession", "meditation", "journey"]
    title: str
    first_name: str
    content: str
    details: str | None
    growth_areas: list[str]
    life_phase_tags: list[str]
    tags: list[str]
    contains_sensitive_content: bool
    status: Literal["pending", "reviewed", "accepted", "rejected"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LiberationPlanResponse(BaseModel):
    id: str
    title: str
    description: str
    price_cents: int
    days_count: int

    model_config = ConfigDict(from_attributes=True)


class StartCheckoutRequest(BaseModel):
    plan_id: str


class StartCheckoutResponse(BaseModel):
    enrollment_id: str
    checkout_status: str
    payment_status: str


class LiberationEnrollmentResponse(BaseModel):
    id: str
    user_id: str
    plan_id: str
    status: Literal["active", "completed", "cancelled"]
    payment_status: str
    start_date: date
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DayProgressResponse(BaseModel):
    id: str
    enrollment_id: str
    day_number: int
    title: str
    status: Literal["locked", "ready", "completed"]
    energy_level: int | None = None
    reflection_note: str | None = None
    carry_forward: str | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CompleteDayRequest(BaseModel):
    energy_level: int = Field(ge=0, le=10)
    reflection_note: str | None = None
    carry_forward: str | None = None


class CompletionSummaryResponse(BaseModel):
    enrollment_id: str
    total_days: int
    completed_days: int
    is_complete: bool


class WebhookRequest(BaseModel):
    enrollment_id: str
    event: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    message: str
