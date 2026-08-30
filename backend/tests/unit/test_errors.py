"""Unit tests for domain exceptions and error handling."""

from app.core.errors import (
    AegisAuthenticationError,
    AegisAuthorizationError,
    AegisException,
    AegisNotFoundError,
    AegisValidationError,
    DatabaseConnectionError,
    ExternalServiceError,
    InfrastructureError,
    QdrantConnectionError,
    RedisConnectionError,
)


def test_exception_hierarchy():
    exc = AegisValidationError("Invalid payload", details={"field": "objective"})
    assert isinstance(exc, AegisException)
    assert exc.status_code == 422
    assert exc.message == "Invalid payload"
    assert exc.details == {"field": "objective"}

    not_found = AegisNotFoundError("Task not found")
    assert not_found.status_code == 404

    auth_err = AegisAuthenticationError("Missing token")
    assert auth_err.status_code == 401

    perm_err = AegisAuthorizationError("Forbidden")
    assert perm_err.status_code == 403

    db_err = DatabaseConnectionError("Postgres unreachable")
    assert isinstance(db_err, InfrastructureError)
    assert db_err.status_code == 503

    redis_err = RedisConnectionError("Redis timeout")
    assert isinstance(redis_err, InfrastructureError)
    assert redis_err.status_code == 503

    qdrant_err = QdrantConnectionError("Qdrant collection error")
    assert isinstance(qdrant_err, InfrastructureError)
    assert qdrant_err.status_code == 503

    ext_err = ExternalServiceError("LLM rate limit reached")
    assert ext_err.status_code == 502
