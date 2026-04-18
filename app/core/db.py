from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings


DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    DATABASE_URL, 
    echo=False,  # CRITICAL: Do not print SQL queries in production (protects PII data and saves logs)
    future=True,
    pool_size=10,        # Handle up to 10 steady concurrent database connections
    max_overflow=20,     # Allow bursting up to 20 additional connections under heavy load
    pool_timeout=30,     # Wait up to 30 seconds for a connection to become available
    pool_recycle=1800,   # Recycle connections every 30 minutes to prevent stale connections
)
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