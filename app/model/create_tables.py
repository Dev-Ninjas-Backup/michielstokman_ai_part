from app.core.db import engine, Base
from app.model.user import User, UserOAuthAccount
from app.model.profile import UserProfile
from app.model.story import Story  # noqa: F401 — must be imported so SQLAlchemy registers the table

def main():
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")

if __name__ == "__main__":
    main()