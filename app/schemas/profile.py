from typing import Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

class UserProfileBase(BaseModel):
    # Step 1: Demographics
    true_name: Optional[str] = None
    age: Optional[int] = None
    country: Optional[str] = None
    city: Optional[str] = None
    height: Optional[str] = None
    education: Optional[str] = None
    annual_income: Optional[str] = None
    gender: Optional[str] = None
    sexual_orientation: Optional[str] = None

    # Step 2: Life Phase & Bio
    life_phase: Optional[str] = None
    bio: Optional[str] = None

    # Step 3: Priorities (Slider values)
    slider_desire_relationship: Optional[float] = None
    slider_life_purpose: Optional[float] = None
    slider_career_money: Optional[float] = None
    slider_true_self: Optional[float] = None
    slider_sexuality_life_energy: Optional[float] = None
    slider_fear_freedom: Optional[float] = None
    slider_health_body: Optional[float] = None
    slider_enlightenment: Optional[float] = None

class UserProfileUpdate(UserProfileBase):
    pass

class UserProfileResponse(UserProfileBase):
    id: UUID
    user_id: UUID
    
    # Calculated stats for the Profile UI
    daily_credits: Optional[str] = "3/3 Remaining"
    reflections_count: int = 0
    avg_resonance: float = 0.0

    model_config = ConfigDict(from_attributes=True)
