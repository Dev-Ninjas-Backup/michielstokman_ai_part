from typing import Optional
from sqlalchemy.orm import Session
from app.model.user import User, UserOAuthAccount

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Retrieve a user by their UUID."""
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Retrieve a user by their email address."""
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, email: str, password_hash: Optional[str] = None) -> User:
    """Create a new regular or OAuth user."""
    db_user = User(
        email=email,
        password_hash=password_hash
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_oauth(db: Session, provider: str, provider_account_id: str) -> Optional[User]:
    """Look up a user based on their specific OAuth provider credentials."""
    oauth_account = db.query(UserOAuthAccount).filter(
        UserOAuthAccount.provider == provider,
        UserOAuthAccount.provider_account_id == provider_account_id
    ).first()
    
    if oauth_account:
        return oauth_account.user
    return None

def link_oauth_account(db: Session, user_id: str, provider: str, provider_account_id: str) -> UserOAuthAccount:
    """Link an additional or new OAuth login source to an existing user."""
    oauth_account = UserOAuthAccount(
        user_id=user_id,
        provider=provider,
        provider_account_id=provider_account_id
    )
    db.add(oauth_account)
    db.commit()
    db.refresh(oauth_account)
    return oauth_account

def update_last_login(db: Session, user: User) -> User:
    """Update the last_login timestamp."""
    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user

def increment_token_version(db: Session, user: User) -> User:
    """Increment the token_version to invalidate all existing tokens."""
    user.token_version += 1
    db.commit()
    db.refresh(user)
    return user

def count_total_users(db: Session) -> int:
    """Get total count of all users."""
    return db.query(User).count()

def count_active_users_30d(db: Session) -> int:
    """Get count of users who logged in in the last 30 days."""
    from datetime import datetime, timedelta, timezone
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    return db.query(User).filter(User.last_login >= thirty_days_ago).count()

def count_verified_users(db: Session) -> int:
    """Get count of verified users."""
    return db.query(User).filter(User.is_verified.is_(True)).count()
    db.commit()
    db.refresh(user)
    return user
