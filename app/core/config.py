import os
from dotenv import load_dotenv
load_dotenv()


class Settings:
    def __init__(self) -> None:
        # --- API Keys ---
        self.XAI_API_KEY: str | None = os.getenv("XAI_API_KEY")
        self.ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")
        self.OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
        # Portrait model for the template cover pipeline (gpt-image family in
        # production; set via OPENAI_IMAGE_MODEL). dall-e-3 still supported.
        self.OPENAI_IMAGE_MODEL: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
        # Cover pipeline switch — instantly revertible.
        # "dalle"            → Grok collage prompt + OpenAI Images (full scrapbook cover)
        # "template" / "v1"  → HTML cover_template + OpenAI portrait in photo hole (V1)
        # "v2"               → Direct OpenAI prompt generation with editorial Polaroid design (V2)
        _cover_method = (os.getenv("COVER_GENERATION_METHOD") or "dalle").strip().lower()
        if _cover_method not in ("dalle", "template", "v1", "v2"):
            _cover_method = "dalle"
        self.COVER_GENERATION_METHOD: str = _cover_method

        # --- SuperGrok (xAI) or Alternative LLM settings ---
        self.LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
        # Model name — swap to grok-3-mini for faster/cheaper calls
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "grok-3")
        # Temperature for story generation (higher = more creative)
        self.LLM_TEMPERATURE_STORY: float = float(os.getenv("LLM_TEMPERATURE_STORY", "0.85"))
        # Temperature for resonance questions (lower = more focused)
        self.LLM_TEMPERATURE_RESONANCE: float = float(os.getenv("LLM_TEMPERATURE_RESONANCE", "0.7"))

        # --- ElevenLabs TTS settings ---
        # Voice ID — Sophia by default (client preferred female voice)
        # Find other voice IDs at: https://elevenlabs.io/voice-library
        self.ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "u8ADrbquiJqufR9XMtb8")
        # TTS model — eleven_turbo_v2_5 is recommended for speed and long-form (40k char limit)
        self.ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
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
        self.APP_ENV: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
        self._is_production = self.APP_ENV in ("production", "prod")
        secret_key = os.getenv("SECRET_KEY")
        if not secret_key:
            if self._is_production:
                raise RuntimeError("SECRET_KEY must be set when APP_ENV is production")
            secret_key = "dev_fallback_secret_key_change_in_prod"
        self.SECRET_KEY: str = secret_key
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "21600"))
        self.GUEST_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("GUEST_TOKEN_EXPIRE_MINUTES", "1440"))

        # App Frontend / External
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
        self.BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
        
        # Security: Allowed CORS origins (comma-separated string in .env)
        origins_raw = os.getenv("ALLOWED_ORIGINS")
        if not origins_raw:
            if self._is_production:
                raise RuntimeError("ALLOWED_ORIGINS must be set when APP_ENV is production")
            origins_raw = "http://localhost:3000"
        self.ALLOWED_ORIGINS: list[str] = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]
        if self._is_production and "*" in self.ALLOWED_ORIGINS:
            raise RuntimeError("ALLOWED_ORIGINS cannot include '*' when APP_ENV is production")
        
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
