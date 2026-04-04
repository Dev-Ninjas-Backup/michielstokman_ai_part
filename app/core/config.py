import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        # LLM Settings
        self.XAI_API_KEY: str | None = os.getenv("XAI_API_KEY")
        self.ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")

        # Vector DB Settings
        self.PINECONE_API_KEY: str | None = os.getenv("PINECONE_API_KEY")
        self.PINECONE_ENVIRONMENT: str | None = os.getenv("PINECONE_ENVIRONMENT")

        # Database Settings
        self.DB_USER: str = os.getenv("DB_USER", "postgres")
        self.DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
        self.DB_HOST: str = os.getenv("DB_HOST", "localhost")
        self.DB_PORT: str = os.getenv("DB_PORT", "5432")
        self.DB_NAME: str = os.getenv("DB_NAME", "michielstokman_db")

        # S3 Settings
        self.AWS_ACCESS_KEY_ID: str | None = os.getenv("AWS_ACCESS_KEY_ID")
        self.AWS_SECRET_ACCESS_KEY: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.AWS_BUCKET_NAME: str | None = os.getenv("AWS_BUCKET_NAME")

        # Security / JWT
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "dev_fallback_secret_key_change_in_prod")
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

    @property
    def DATABASE_URL(self) -> str:
        """Constructs the SQLAlchemy sync PostgreSQL connection string."""
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()
