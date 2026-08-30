"""Domain exceptions for the AEGIS Tool subsystem."""

from typing import Any

from fastapi import status

from app.core.errors import (
    AegisAuthorizationError,
    AegisException,
    AegisNotFoundError,
    AegisValidationError,
    ExternalServiceError,
)


class ToolError(AegisException):
    """Base exception for all tool-related errors."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ToolNotFoundError(ToolError, AegisNotFoundError):
    """Raised when an requested tool is not found in the registry."""

    status_code = status.HTTP_404_NOT_FOUND


class ToolValidationError(ToolError, AegisValidationError):
    """Raised when tool parameters fail schema validation or contain invalid values."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ToolExecutionError(ToolError):
    """Raised when tool logic fails during execution (e.g. division by zero, invalid operation)."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details=details)


class ToolTimeoutError(ToolError, ExternalServiceError):
    """Raised when tool execution exceeds its configured timeout threshold."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT


class ToolPolicyViolationError(ToolError, AegisAuthorizationError):
    """Raised when an invocation is rejected by security policy (e.g. RESTRICTED/DANGEROUS)."""

    status_code = status.HTTP_403_FORBIDDEN


class ToolRegistrationError(ToolError, AegisValidationError):
    """Raised when registering an invalid tool or attempting duplicate tool registration."""

    status_code = status.HTTP_409_CONFLICT
