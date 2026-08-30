"""Domain exceptions for ABAC evaluations."""

from app.core.errors import AegisException


class ABACError(AegisException):
    """Base exception for ABAC evaluation errors."""

    status_code = 403


class ABACPolicyDeniedError(ABACError):
    """Raised when an ABAC policy rule denies authorization."""

    status_code = 403
