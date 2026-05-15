
import uuid
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.security import create_access_token

# Import ALL models to avoid Mapper errors
from app.model.user import User
from app.model.profile import UserProfile
from app.model.subscription import UserSubscription
from app.model.billing import PaymentTransaction
from app.model.liberation import LiberationDefinition, LiberationDayDefinition, UserJourney, UserJourneyStep

# Use the local DB settings from .env
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

try:
    # Find any user
    user = db.query(User).first()
    if user:
        token = create_access_token(data={"sub": user.email})
        print(f"USER_ID: {user.id}")
        print(f"USER_EMAIL: {user.email}")
        print(f"TOKEN: {token}")
    else:
        print("NO_USER_FOUND")
finally:
    db.close()
