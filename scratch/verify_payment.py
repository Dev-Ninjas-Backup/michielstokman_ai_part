# scratch/verify_payment.py
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

USER_ID = UUID("c767bb09-f8f5-4a95-9a61-1e39afd7c379")

def verify():
    db = SessionLocal()
    try:
        # Check payments
        payments = db.query(PaymentTransaction).filter(PaymentTransaction.user_id == USER_ID).all()
        print(f"--- PAYMENTS ({len(payments)}) ---")
        for p in payments:
            print(f"ID: {p.id} | Status: {p.status.value} | Amount: {p.amount_cents/100} {p.currency}")
            
        # Check subscription
        sub = db.query(UserSubscription).filter(UserSubscription.user_id == USER_ID).order_by(UserSubscription.created_at.desc()).first()
        print("\n--- LATEST SUBSCRIPTION ---")
        if sub:
            print(f"ID: {sub.id} | Status: {sub.status.value} | End Date: {sub.current_period_end}")
        else:
            print("No subscription found yet.")
            
    finally:
        db.close()

if __name__ == "__main__":
    verify()
