"""
Application configuration — loads from environment variables.
All sensitive values must be set via environment; never hardcoded.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── Core ─────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "production"
    PROJECT_NAME: str = "Anonymous Signal"

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://anon_user:password@localhost:5432/anon_signal"

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── Encryption ───────────────────────────────────────────────────────────
    ENCRYPTION_KEY: str = ""  # Fernet key — MUST be set in production

    # ─── JWT / Auth ───────────────────────────────────────────────────────────
    JWT_SECRET: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # ─── AI Service ───────────────────────────────────────────────────────────
    AI_SERVICE_URL: str = "http://ai-service:8001"

    # ─── Privacy Settings (IMMUTABLE in production) ───────────────────────────
    DISABLE_ACCESS_LOGS: bool = True
    STORE_IP_ADDRESSES: bool = False   # MUST remain False
    STORE_USER_AGENTS: bool = False    # MUST remain False

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_SUBMISSIONS: int = 10     # max submissions per window
    RATE_LIMIT_WINDOW_SECONDS: int = 300  # 5 minutes

    # ─── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # ─── Trusted Hosts ────────────────────────────────────────────────────────
    ALLOWED_HOSTS: List[str] = ["*"]

    # ─── File Upload Limits ───────────────────────────────────────────────────
    MAX_AUDIO_SIZE_MB: int = 10
    MAX_IMAGE_SIZE_MB: int = 5
    UPLOAD_DIR: str = "/app/encrypted_uploads"

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str, info) -> str:
        """Warn if encryption key is not set in production."""
        if not v:
            import warnings
            warnings.warn(
                "ENCRYPTION_KEY not set! Reports will not be encrypted. "
                "Set ENCRYPTION_KEY in production!",
                SecurityWarning,
                stacklevel=2,
            )
        return v


settings = Settings()
