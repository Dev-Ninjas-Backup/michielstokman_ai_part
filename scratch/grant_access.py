
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.model.user import User
from app.model.subscription import UserSubscription

# Use the local DB settings from .env
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

try:
    # Find the test user
    user = db.query(User).first()
    if user:
        # Check if they already have the subscription
        existing = db.query(UserSubscription).filter(
            UserSubscription.user_id == user.id,
            UserSubscription.plan_code == "deep_presence"
        ).first()

        if not existing:
            new_sub = UserSubscription(
                user_id=user.id,
                plan_code="deep_presence",
                status="active"
            )
            db.add(new_sub)
            db.commit()
            print(f"SUCCESS: Granted 'deep_presence' access to {user.email}")
        else:
            print(f"ALREADY_HAS_ACCESS: {user.email}")
    else:
        print("NO_USER_FOUND")
finally:
    db.close()
