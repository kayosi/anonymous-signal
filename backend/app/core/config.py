"""
Application configuration — loads from environment variables.
All sensitive values must be set via environment; never hardcoded.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import secrets


def parse_str_list(v) -> List[str]:
    """Parse a list from env var — handles comma-separated strings, JSON arrays, or actual lists."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return []
        if v.startswith("["):
            import json
            return json.loads(v)
        return [i.strip() for i in v.split(",") if i.strip()]
    return [str(v)]


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
    ENCRYPTION_KEY: str = ""

    # ─── JWT / Auth ───────────────────────────────────────────────────────────
    JWT_SECRET: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # ─── AI Service ───────────────────────────────────────────────────────────
    AI_SERVICE_URL: str = "http://ai-service:8001"

    # ─── Privacy Settings ─────────────────────────────────────────────────────
    DISABLE_ACCESS_LOGS: bool = True
    STORE_IP_ADDRESSES: bool = False
    STORE_USER_AGENTS: bool = False

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_SUBMISSIONS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 300

    # ─── CORS — stored as plain string, parsed via validator ──────────────────
    # Using str instead of List[str] to prevent pydantic-settings from
    # intercepting and JSON-parsing the value before our validator runs.
    CORS_ORIGINS_STR: str = "http://localhost:3000"
    ALLOWED_HOSTS_STR: str = "*"

    # ─── File Upload Limits ───────────────────────────────────────────────────
    MAX_AUDIO_SIZE_MB: int = 10
    MAX_IMAGE_SIZE_MB: int = 5
    UPLOAD_DIR: str = "/app/encrypted_uploads"

    # ─── Scheduler ────────────────────────────────────────────────────────────
    SCHEDULER_INTERVAL_SECONDS: int = 300

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return parse_str_list(self.CORS_ORIGINS_STR)

    @property
    def ALLOWED_HOSTS(self) -> List[str]:
        return parse_str_list(self.ALLOWED_HOSTS_STR)

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if not v:
            import warnings
            warnings.warn(
                "ENCRYPTION_KEY not set! Reports will not be encrypted.",
                stacklevel=2,
            )
        return v


settings = Settings()