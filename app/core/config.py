import os
from dotenv import load_dotenv
load_dotenv()


class Settings:
    def __init__(self) -> None:
        # --- API Keys ---
        self.XAI_API_KEY: str | None = os.getenv("XAI_API_KEY")
        self.ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")

        # --- SuperGrok (xAI) or Alternative LLM settings ---
        self.LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
        # Model name — swap to grok-3-mini for faster/cheaper calls
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "grok-3")
        # Temperature for story generation (higher = more creative)
        self.LLM_TEMPERATURE_STORY: float = float(os.getenv("LLM_TEMPERATURE_STORY", "0.85"))
        # Temperature for resonance questions (lower = more focused)
        self.LLM_TEMPERATURE_RESONANCE: float = float(os.getenv("LLM_TEMPERATURE_RESONANCE", "0.7"))

        # --- ElevenLabs TTS settings ---
        # Voice ID — Rachel by default (warm, professional female voice)
        # Find other voice IDs at: https://elevenlabs.io/voice-library
        self.ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        # TTS model — eleven_turbo_v2_5 is recommended for speed and long-form (40k char limit)
        self.ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
        # Voice stability (0.0-1.0): higher = more consistent, warmer delivery
        self.ELEVENLABS_STABILITY: float = float(os.getenv("ELEVENLABS_STABILITY", "0.65"))
        # Similarity boost (0.0-1.0): higher = more expressive, less robotic
        self.ELEVENLABS_SIMILARITY_BOOST: float = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.80"))
        # Style (0.0-1.0): subtle stylistic variation
        self.ELEVENLABS_STYLE: float = float(os.getenv("ELEVENLABS_STYLE", "0.30"))

        # Vector DB Settings
        self.PINECONE_API_KEY: str | None = os.getenv("PINECONE_API_KEY")
        self.PINECONE_ENVIRONMENT: str | None = os.getenv("PINECONE_ENVIRONMENT")
        self.PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "stories-rag")

        # Database Settings
        self.DB_USER: str = os.getenv("DB_USER", "postgres")
        self.DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
        self.DB_HOST: str = os.getenv("DB_HOST", "localhost")
        self.DB_PORT: str = os.getenv("DB_PORT", "5432")
        self.DB_NAME: str = os.getenv("DB_NAME", "michielstokman_db")

        # S3 Settings
        self.AWS_ACCESS_KEY_ID: str | None = os.getenv("AWS_ACCESS_KEY_ID")
        self.AWS_SECRET_ACCESS_KEY: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.AWS_REGION_NAME: str = os.getenv("AWS_REGION_NAME", "us-east-1")
        self.AWS_BUCKET_NAME: str | None = os.getenv("AWS_BUCKET_NAME")

        # Stripe Settings
        self.STRIPE_API_KEY: str | None = os.getenv("STRIPE_API_KEY")
        self.STRIPE_WEBHOOK_SECRET: str | None = os.getenv("STRIPE_WEBHOOK_SECRET")

        # Security / JWT
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "dev_fallback_secret_key_change_in_prod")
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
        self.GUEST_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("GUEST_TOKEN_EXPIRE_MINUTES", "1440"))

        # App Frontend / External
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
        self.BACKEND_URL: str = os.getenv("BACKEND_URL", "http://34.255.26.146:8000").rstrip("/")
        
        # Security: Allowed CORS origins (comma-separated string in .env)
        self.ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")
        
        # Social Auth
        self.GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID")
        self.FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "shejan-a82dd")
        
        # Firebase service account (from .env as base64-encoded JSON)
        import base64
        import json
        firebase_service_account_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        if firebase_service_account_b64:
            try:
                firebase_json_str = base64.b64decode(firebase_service_account_b64).decode('utf-8')
                self.FIREBASE_SERVICE_ACCOUNT_JSON = json.loads(firebase_json_str)
            except Exception:
                self.FIREBASE_SERVICE_ACCOUNT_JSON = None
        else:
            self.FIREBASE_SERVICE_ACCOUNT_JSON = None

    @property
    def DATABASE_URL(self) -> str:
        """Constructs the SQLAlchemy sync PostgreSQL connection string."""
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()
