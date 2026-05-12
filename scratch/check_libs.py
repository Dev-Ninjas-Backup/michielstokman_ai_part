from app.core.db import SessionLocal
from app.model.liberation import LiberationDefinition

db = SessionLocal()
try:
    libs = db.query(LiberationDefinition).all()
    print(f"Found {len(libs)} liberation definitions.")
    for lib in libs:
        print(f"- {lib.title} ({lib.journey_code}): status={lib.moderation_status}, active={lib.is_active}")
finally:
    db.close()
