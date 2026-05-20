import sys
import os
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.db import SessionLocal
from app.model.user import User
from app.model.profile import UserProfile
from app.services.service_profile import process_profile_update
from app.schemas.profile import UserProfileUpdate

def run_test():
    print("==================================================")
    print("RUNNING PROFILE SETUP FLAG UNIT TEST")
    print("==================================================")
    
    db = SessionLocal()
    test_email = f"profile_test_{uuid.uuid4().hex[:6]}@example.com"
    user_id = None
    
    try:
        # 1. Create a new user (simulate signup)
        user = User(
            id=uuid.uuid4(),
            email=test_email,
            password_hash="fakehash",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        
        print(f"Created test user: {test_email}")
        print(f"Initial is_profile_setup status: {user.is_profile_setup}")
        assert user.is_profile_setup is False, "Expected initial profile setup status to be False"
        
        # 2. Update their profile (simulate onboarding completion)
        profile_update = UserProfileUpdate(
            true_name="Test User",
            age=25,
            country="Netherlands",
            city="Amsterdam",
            life_phase="Career Focus",
            bio="A test user biography",
            gender="Male",
            slider_desire_relationship=3.5,
            slider_life_purpose=4.0
        )
        
        print("Updating user profile...")
        profile = process_profile_update(db, user_id=str(user_id), profile_update=profile_update)
        
        # Refresh user instance from DB
        db.refresh(user)
        print(f"Post-update is_profile_setup status: {user.is_profile_setup}")
        assert user.is_profile_setup is True, "Expected profile setup status to be True after profile update"
        
        print("ALL TESTS PASSED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if user_id:
            db.query(UserProfile).filter(UserProfile.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()
            print("Cleanup complete!")
        db.close()

if __name__ == "__main__":
    run_test()
