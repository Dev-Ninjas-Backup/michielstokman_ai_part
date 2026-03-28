import os
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    # LLM Settings
    XAI_API_KEY: str = Field(..., env="XAI_API_KEY")
    ELEVENLABS_API_KEY: str = Field(..., env="ELEVENLABS_API_KEY")

    # Vector DB Settings
    PINECONE_API_KEY: str = Field(..., env="PINECONE_API_KEY")
    PINECONE_ENVIRONMENT: str = Field(..., env="PINECONE_ENVIRONMENT")

    # Database Settings
    DB_USER: str = Field("postgres", env="DB_USER")
    DB_PASSWORD: str = Field("password", env="DB_PASSWORD")
    DB_HOST: str = Field("localhost", env="DB_HOST")
    DB_PORT: str = Field("5432", env="DB_PORT")
    DB_NAME: str = Field("michielstokman_db", env="DB_NAME")

    # S3 Settings
    AWS_ACCESS_KEY_ID: str = Field(None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = Field(None, env="AWS_SECRET_ACCESS_KEY")
    AWS_BUCKET_NAME: str = Field(None, env="AWS_BUCKET_NAME")

    @property
    def DATABASE_URL(self) -> str:
        """Constructs the async PostgreSQL connection string."""
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"

settings = Settings()
