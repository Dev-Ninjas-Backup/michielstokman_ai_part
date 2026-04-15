from sqlalchemy import text
from app.core.db import engine, Base
from app.model.user import User, UserOAuthAccount
from app.model.profile import UserProfile
from app.model.story import Story
from app.model.billing import SubscriptionPlan, UserSubscription, PaymentTransaction

def main():
    with engine.connect() as conn:
        print("⚠️  Dropping all existing tables (with CASCADE)...")
        # We use raw SQL for CASCADE to ensure everything dies regardless of import order
        conn.execute(text("DROP TABLE IF EXISTS users, user_oauth_accounts, user_profiles, stories, subscription_plans, user_subscriptions, payment_transactions CASCADE;"))
        conn.commit()
    
    print("✨ Creating all tables with new schema...")
    Base.metadata.create_all(bind=engine)
    
    print("✅ Done! The database is fresh and ready.")

if __name__ == "__main__":
    main()
