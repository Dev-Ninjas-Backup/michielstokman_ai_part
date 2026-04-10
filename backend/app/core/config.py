import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Transform To Liberation Backend")
    api_prefix: str = os.getenv("API_PREFIX", "/v1")
    secret_key: str = os.getenv("SECRET_KEY", "change-this-in-production")
    algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./backend.db")


settings = Settings()
