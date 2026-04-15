from sqlalchemy.orm import Session
from app.model.profile import UserProfile
from app.schemas.profile import UserProfileUpdate

def get_user_profile(db: Session, user_id: str) -> UserProfile:
    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

def create_or_update_user_profile(db: Session, user_id: str, profile_data: UserProfileUpdate) -> UserProfile:
    profile = get_user_profile(db, user_id)
    
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    
    # Update profile fields based on data provided
    update_data = profile_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
        
    db.commit()
    db.refresh(profile)
    return profile
