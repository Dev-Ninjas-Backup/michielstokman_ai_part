import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.db import engine, Base
from app.model.user import User, UserOAuthAccount
from app.model.billing import SubscriptionPlan, UserSubscription, PaymentTransaction
from app.model.profile import UserProfile
from app.model.story import Story
from app.model.feedback import StoryFeedback
from app.model.credit import UserCredit

def drop_all_tables():
    from sqlalchemy import text
    with engine.connect() as conn:
        print("⚠️ Dropping all existing tables cascades to generate a clean slate...")
        conn.execute(text("DROP TABLE IF EXISTS users, user_oauth_accounts, user_profiles, stories, subscription_plans, user_subscriptions, payment_transactions, user_credits, story_feedback, alembic_version CASCADE;"))
        conn.commit()
    print("✅ All tables dropped. Database is completely empty.")

if __name__ == "__main__":
    drop_all_tables()
