from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.profile import UserProfileUpdate
from app.data.profile import get_user_profile, create_or_update_user_profile

def process_profile_update(db: Session, user_id: str, profile_update: UserProfileUpdate):
    try:
        updated_profile = create_or_update_user_profile(db, user_id, profile_update)
        return updated_profile
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )

def get_current_user_profile(db: Session, user_id: str):
    profile = get_user_profile(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile
