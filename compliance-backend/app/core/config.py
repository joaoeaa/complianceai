"""
Application settings loaded from environment variables.
Uses pydantic-settings for validation and type coercion.
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    # ─── App ───
    APP_NAME: str = "ComplianceAI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ─── Database ───
    DATABASE_URL: str = "postgresql+asyncpg://compliance_user:compliance_pass@localhost:5432/compliance_db"
    DATABASE_URL_SYNC: str = "postgresql://compliance_user:compliance_pass@localhost:5432/compliance_db"

    # ─── Redis ───
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── Auth ───
    SECRET_KEY: str = "change-me-in-production-32-chars-minimum"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Anthropic ───
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MAX_TOKENS: int = 4096
    ANTHROPIC_TIMEOUT: int = 120

    # ─── OpenAI (Embeddings) ───
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536

    # ─── Storage ───
    UPLOAD_DIR: str = "./storage/uploads"
    MAX_FILE_SIZE_MB: int = 10

    # ─── Celery ───
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ─── CORS ───
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:5176"]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
