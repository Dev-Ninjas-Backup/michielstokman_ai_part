from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.schemas.profile import UserProfileUpdate
from app.data.profile import get_user_profile, create_or_update_user_profile
from app.data.credit import is_premium_user, get_or_create_credit
from app.model.story import Story, GenerationStatus

def process_profile_update(db: Session, user_id: str, profile_update: UserProfileUpdate):
    try:
        updated_profile = create_or_update_user_profile(db, user_id, profile_update)
        
        # Set user's profile setup status to True
        from app.data.user import get_user_by_id
        user = get_user_by_id(db, user_id)
        if user and not user.is_profile_setup:
            user.is_profile_setup = True
            db.commit()
            
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
    
    # 1. Calculate Daily Credits status string
    premium = is_premium_user(db, user_id)
    if premium:
        profile.daily_credits = "Premium — Unlimited"
    else:
        credit = get_or_create_credit(db, user_id)
        profile.daily_credits = f"{credit.daily_credits_remaining}/{credit.max_daily_credits} Remaining"

    # 2. Calculate Stats (Reflections & Avg Resonance)
    stats = db.query(
        func.count(Story.id).label("reflections"),
        func.avg(Story.pulse_score).label("resonance")
    ).filter(
        Story.user_id == user_id,
        Story.generation_status == GenerationStatus.completed
    ).first()

    profile.reflections_count = stats.reflections or 0
    profile.avg_resonance = round(float(stats.resonance or 0.0), 1)

    return profile
