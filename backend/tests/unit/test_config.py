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


def test_production_missing_secret_fails_startup():
    import pytest
    with pytest.raises(ValueError, match="Production configuration error"):
        Settings(ENVIRONMENT=Environment.PRODUCTION)


def test_production_short_secret_fails_startup():
    import pytest
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(ENVIRONMENT=Environment.PRODUCTION, SECRET_KEY="too_short_secret")


def test_production_valid_secret_key_succeeds():
    secure_secret = "a" * 32
    settings = Settings(ENVIRONMENT=Environment.PRODUCTION, SECRET_KEY=secure_secret)
    assert settings.effective_jwt_secret == secure_secret


def test_production_valid_jwt_secret_succeeds():
    secure_jwt_secret = "b" * 32
    settings = Settings(ENVIRONMENT=Environment.PRODUCTION, JWT_SECRET=secure_jwt_secret)
    assert settings.effective_jwt_secret == secure_jwt_secret


def test_cors_origins_parsing():
    # Production without CORS_ORIGINS defaults to []
    prod_settings = Settings(
        ENVIRONMENT=Environment.PRODUCTION,
        SECRET_KEY="x" * 32,
        CORS_ORIGINS="",
    )
    assert prod_settings.cors_origins_list == []

    # Production with specific comma-separated origins
    prod_with_origins = Settings(
        ENVIRONMENT=Environment.PRODUCTION,
        SECRET_KEY="x" * 32,
        CORS_ORIGINS="https://app.aegis.io, https://admin.aegis.io",
    )
    assert prod_with_origins.cors_origins_list == ["https://app.aegis.io", "https://admin.aegis.io"]

    # Development without CORS_ORIGINS defaults to ["*"]
    dev_settings = Settings(ENVIRONMENT=Environment.DEVELOPMENT, CORS_ORIGINS="")
    assert dev_settings.cors_origins_list == ["*"]

