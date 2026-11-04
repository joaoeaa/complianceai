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
    # Ligado, o SQLAlchemy loga cada consulta e o log vai para DEBUG. Desligado
    # por padrão para que esquecer a variável em produção não seja o caro.
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ─── Database ───
    DATABASE_URL: str = "postgresql+asyncpg://compliance_user:compliance_pass@localhost:5432/compliance_db"
    DATABASE_URL_SYNC: str = "postgresql://compliance_user:compliance_pass@localhost:5432/compliance_db"

    # ─── Auth ───
    SECRET_KEY: str = "change-me-in-production-32-chars-minimum"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Anthropic ───
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    # Teto de saída. Um contrato longo com muitos alertas passava de 8192, e a
    # resposta vinha cortada no meio de uma string, o que só aparecia depois como
    # "JSON inválido". O modelo suporta bem mais do que isto.
    ANTHROPIC_MAX_TOKENS: int = 16384
    ANTHROPIC_TIMEOUT: int = 300

    # ─── OpenAI (Embeddings) ───
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536

    # ─── Storage ───
    # Onde fica o arquivo original: "local" (UPLOAD_DIR) ou "s3" (bucket
    # compatível com S3: Supabase Storage, Cloudflare R2, AWS). Ver services/storage.py.
    STORAGE_BACKEND: str = "local"
    UPLOAD_DIR: str = "./storage/uploads"
    MAX_FILE_SIZE_MB: int = 10
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_REGION: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_PREFIX: str = "uploads/"

    # ─── Análise em background ───
    # Análises simultâneas no processo da api. Cada uma segura uma conexão com o
    # banco e uma chamada longa à Anthropic.
    ANALYSIS_MAX_CONCURRENT: int = 2
    # Sem sinal de vida por este tempo, a análise é dada como órfã e vira erro.
    # Precisa passar com folga do intervalo do batimento (60s) e do maior intervalo
    # entre duas atualizações sem batimento: uma chamada ao LLM mais o backoff.
    ORPHAN_TIMEOUT_MINUTES: int = 12
    # Teto do batimento, contado do início da primeira tentativa. Passado isto, a
    # análise deixa de ser renovada e vira órfã no prazo acima: uma thread travada
    # não segura o documento em processing para sempre.
    ANALYSIS_MAX_DURATION_MINUTES: int = 30

    # ─── CORS ───
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:5176"]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Variável que a aplicação não conhece é ignorada, e não erro de boot. Um
        # .env antigo, com REDIS_URL e CELERY_* da época do worker, derrubava a api.
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
