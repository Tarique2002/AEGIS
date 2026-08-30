"""Unit tests for configuration management."""

from app.core.config import Environment, Settings


def test_default_settings():
    settings = Settings()
    assert settings.APP_NAME == "AEGIS"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.ENVIRONMENT in [Environment.DEVELOPMENT, Environment.TESTING]
    assert settings.API_V1_PREFIX == "/api/v1"
    assert "postgresql+asyncpg://" in settings.async_database_url
    assert "redis://" in settings.redis_connection_url
    assert "http://" in settings.qdrant_connection_url


def test_custom_database_url_override():
    settings = Settings(DATABASE_URL="postgresql://user:pass@remote:5433/prod_db")
    assert settings.async_database_url == "postgresql+asyncpg://user:pass@remote:5433/prod_db"


def test_redis_connection_url_with_password():
    settings = Settings(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6380,
        REDIS_PASSWORD="secure_password",
        REDIS_DB=2,
    )
    assert settings.redis_connection_url == "redis://:secure_password@redis.example.com:6380/2"


def test_qdrant_connection_url_override():
    settings = Settings(QDRANT_URL="https://qdrant.cloud.io:6333")
    assert settings.qdrant_connection_url == "https://qdrant.cloud.io:6333"
