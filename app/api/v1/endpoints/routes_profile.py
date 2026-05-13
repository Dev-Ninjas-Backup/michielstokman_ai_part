from fastapi import APIRouter, Depends, status, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.profile import UserProfileUpdate, UserProfileResponse
from app.services.service_profile import process_profile_update, get_current_user_profile
from app.api.deps import get_current_user
from app.model.user import User
from app.utils.s3 import upload_image_to_s3, delete_s3_object
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


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


@router.put("/me/profile/avatar", response_model=ApiResponse[UserProfileResponse])
async def update_avatar(
    file: UploadFile = File(..., description="Image file (JPEG, PNG, WEBP — max 5 MB)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a profile picture (avatar). 
    Image is stored on AWS S3 and the URL is saved to the profile.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WEBP.",
        )

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Image exceeds the 5 MB size limit.",
        )

    # Upload to S3
    ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
    image_url, s3_key = upload_image_to_s3(image_bytes, file_extension=ext)
    
    if not image_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to upload image to S3.",
        )

    # Update profile
    profile = get_current_user_profile(db, user_id=str(current_user.id))
    
    # Optional: If we tracked s3_key in the profile table, we could delete the old one here.
    # Currently we only store the URL, so we just overwrite it.
    profile.profile_image_url = image_url
    db.commit()
    db.refresh(profile)

    return success_response("Avatar updated successfully", status.HTTP_200_OK, profile)
