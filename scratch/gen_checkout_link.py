# scratch/gen_checkout_link.py
import sys
import os
from uuid import UUID

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import models to satisfy relationships
from app.model.user import User, UserOAuthAccount
from app.model.profile import UserProfile
from app.model.billing import UserSubscription, PaymentTransaction, SubscriptionPlan
from app.core.db import SessionLocal
from app.services.service_billing import BillingService

USER_ID = UUID("c767bb09-f8f5-4a95-9a61-1e39afd7c379")
PLAN_ID = UUID("8c0c8bfa-75aa-491e-9e11-7ff1772c246f")

def gen():
    db = SessionLocal()
    try:
        result = BillingService.start_checkout(
            db=db,
            user_id=USER_ID,
            plan_id=PLAN_ID,
            provider="stripe"
        )
        print(f"CHECKOUT_URL={result['checkout_url']}")
    finally:
        db.close()

if __name__ == "__main__":
    gen()
