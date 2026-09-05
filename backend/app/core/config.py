"""Application configuration management using Pydantic Settings."""

from enum import Enum
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


DEFAULT_SECRET_KEY = "development_secret_key_change_in_production_min_32_chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "AEGIS"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    JWT_SECRET: str | None = None
    JWT_REFRESH_SECRET: str | None = None
    CORS_ORIGINS: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.CORS_ORIGINS or not self.CORS_ORIGINS.strip():
            if self.ENVIRONMENT in (Environment.DEVELOPMENT, Environment.TESTING):
                return ["*"]
            return []
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def effective_jwt_secret(self) -> str:
        return self.JWT_SECRET or self.SECRET_KEY

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        if self.ENVIRONMENT in (Environment.PRODUCTION, Environment.STAGING):
            secret = self.effective_jwt_secret
            if (
                not secret
                or secret == DEFAULT_SECRET_KEY
                or len(secret.strip()) < 32
            ):
                raise ValueError(
                    "Production configuration error: In production/staging environments, "
                    "a secure SECRET_KEY or JWT_SECRET of at least 32 characters must be provided. "
                    "Default or development secret keys are strictly prohibited."
                )
        return self

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"

    # PostgreSQL Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "aegis_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            # Ensure asyncpg driver is specified
            url = str(self.DATABASE_URL)
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0
    REDIS_URL: str | None = None
    REDIS_TIMEOUT_SECONDS: float = 2.0

    @property
    def redis_connection_url(self) -> str:
        if self.REDIS_URL:
            return str(self.REDIS_URL)
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else "@"
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Qdrant Vector Database
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: str | None = None
    QDRANT_URL: str | None = None
    QDRANT_TIMEOUT_SECONDS: int = 3

    @property
    def qdrant_connection_url(self) -> str:
        if self.QDRANT_URL:
            return str(self.QDRANT_URL)
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    # LLM Settings
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "llama3.2"
    LLM_TIMEOUT_SECONDS: float = 60.0
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # Safety & Platform Hardening (Phase 8)
    SAFETY_ENABLED: bool = True
    MAX_RISK_LEVEL: str = "CRITICAL"
    APPROVAL_REQUIRED_ABOVE: str = "MEDIUM"
    RATE_LIMIT_ENABLED: bool = True
    REQUEST_MAX_BYTES: int = 1_048_576  # 1 MB
    AUTH_RATE_LIMIT: int = 20  # requests per minute
    GENERAL_RATE_LIMIT: int = 120
    TOOL_RATE_LIMIT: int = 30
    ORCHESTRATION_RATE_LIMIT: int = 10
    MEMORY_RATE_LIMIT: int = 60
    TOKEN_REVOCATION_ENABLED: bool = True
    APPROVAL_TTL_SECONDS: int = 300  # 5 minutes
    MAX_SAFETY_ACTIONS: int = 100
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_COOLDOWN: float = 60.0
    SAFETY_POLICY_VERSION: str = "1.0.0"

    # Audit Checkpoint & Cryptographic Signing (Phases 9 & 10)
    AUDIT_SIGNING_KEY: str | None = None
    SIGNING_SECRET: str | None = None
    AEGIS_KMS_KEY_ID: str | None = None

    @property
    def effective_signing_key(self) -> str | None:
        return self.AUDIT_SIGNING_KEY or self.SIGNING_SECRET


# Global singleton settings instance
settings = Settings()
