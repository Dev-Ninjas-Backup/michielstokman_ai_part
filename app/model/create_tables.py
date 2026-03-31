from app.core.db import engine, Base
from app.model.user import User, UserOAuthAccount

def main():
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")

if __name__ == "__main__":
    main()