from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings


DATABASE_URL = settings.DATABASE_URL

engine = create_engine(DATABASE_URL, echo=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Test database connection
# from sqlalchemy import text

# if __name__ == "__main__":
#     try:
#         db = next(get_db())
#         db.execute(text("SELECT 1"))
#         print("Database connection successful!")
#     except Exception as e:
#         print("Database connection failed:", e)