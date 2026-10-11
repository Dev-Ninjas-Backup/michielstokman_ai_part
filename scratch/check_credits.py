import sys
from app.core.db import SessionLocal
from app.model.user import User
from app.model.profile import UserProfile
from app.model.billing import UserSubscription, SubscriptionPlan, PaymentTransaction
from app.model.credit import UserCredit
from app.model.feedback import StoryFeedback
from app.model.guest_session import GuestSession
from app.model.liberation import LiberationDefinition, LiberationDayDefinition, UserJourney, UserJourneyStep
from app.model.cover_image import CoverImage
from app.model.story import Story

db = SessionLocal()
users = db.query(User).all()
print(f"Total users: {len(users)}")
for u in users:
    credit = db.query(UserCredit).filter(UserCredit.user_id == u.id).first()
    sub = db.query(UserSubscription).filter(UserSubscription.user_id == u.id).first()
    sub_status = sub.status if sub else "No sub"
    remaining = credit.daily_credits_remaining if credit else "No record"
    print(f"User: {u.id} | Email: {u.email} | Credits remaining: {remaining} | Subscription: {sub_status}")

db.close()
