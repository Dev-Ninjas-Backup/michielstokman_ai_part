from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.profile import UserProfileUpdate, UserProfileResponse
from app.services.service_profile import process_profile_update, get_current_user_profile
from app.api.deps import get_current_user
from app.model.user import User

router = APIRouter()


@router.put("/me/profile", response_model=ApiResponse[UserProfileResponse])
def update_profile(
    profile_data: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Creates or updates the profile information for the current user.
    Called when completing the 3-step onboarding flow.
    """
    profile = process_profile_update(db, user_id=str(current_user.id), profile_update=profile_data)
    return success_response("Profile updated successfully", status.HTTP_200_OK, profile)


@router.get("/me/profile", response_model=ApiResponse[UserProfileResponse])
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the currently logged in user's profile.
    """
    profile = get_current_user_profile(db, user_id=str(current_user.id))
    return success_response("Profile fetched successfully", status.HTTP_200_OK, profile)
