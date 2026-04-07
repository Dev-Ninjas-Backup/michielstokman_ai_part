from app.core.db import engine, Base
from app.model.user import User, UserOAuthAccount
from app.model.profile import UserProfile
from app.model.story import Story

def main():
    print("⚠️  Dropping all existing tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("✨ Creating all tables with new schema...")
    Base.metadata.create_all(bind=engine)
    
    print("✅ Done! The database is fresh and ready.")

if __name__ == "__main__":
    main()
