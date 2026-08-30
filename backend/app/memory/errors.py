"""Domain exceptions for the AEGIS Multi-Layer Memory Engine."""

from typing import Any

from fastapi import status

from app.core.errors import (
    AegisAuthorizationError,
    AegisException,
    AegisNotFoundError,
    AegisValidationError,
    InfrastructureError,
)


class MemoryError(AegisException):
    """Base exception for memory operations."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class MemoryNotFoundError(MemoryError, AegisNotFoundError):
    """Raised when a requested memory item is not found."""

    status_code = status.HTTP_404_NOT_FOUND


class MemoryValidationError(MemoryError, AegisValidationError):
    """Raised when memory content or metadata fails schema validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class MemoryPolicyViolationError(MemoryError, AegisAuthorizationError):
    """Raised when a memory operation violates platform policies (e.g. size, type)."""

    status_code = status.HTTP_403_FORBIDDEN


class MemoryOwnershipError(MemoryPolicyViolationError):
    """Raised when an operation attempts unauthorized access across user boundary."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(
        self,
        message: str = "Unauthorized cross-user memory access.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)


class MemoryStorageError(MemoryError, InfrastructureError):
    """Raised when an underlying memory storage layer (Redis, PostgreSQL, Qdrant) fails."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
