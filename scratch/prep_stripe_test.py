# scratch/prep_stripe_test.py
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import models to satisfy relationships
from app.model.user import User, UserOAuthAccount
from app.model.profile import UserProfile
from app.model.billing import UserSubscription, PaymentTransaction, SubscriptionPlan
from app.core.db import SessionLocal
from app.services.service_billing import BillingService
from app.core.security import get_password_hash

def prep():
    db = SessionLocal()
    try:
        # 1. Ensure plans exist
        BillingService.ensure_default_plans(db)
        
        # 2. Create or get test user
        email = "stripe_test@example.com"
        test_user = db.query(User).filter(User.email == email).first()
        if not test_user:
            test_user = User(
                email=email,
                password_hash=get_password_hash("testpass"),
                is_active=True
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            print(f"CREATED_USER_ID={test_user.id}")
        else:
            print(f"EXISTING_USER_ID={test_user.id}")
            
        # 3. Get first plan
        plans = BillingService.list_plans(db)
        if plans:
            print(f"PLAN_ID={plans[0].id}")
            print(f"PLAN_NAME={plans[0].name}")
        else:
            print("ERROR: No plans found")
            
    finally:
        db.close()

if __name__ == "__main__":
    prep()
