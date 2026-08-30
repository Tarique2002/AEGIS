"""Domain exceptions for CEL Policy compilation and evaluation."""

from app.core.errors import AegisException, AegisValidationError


class CELCompilationError(AegisValidationError):
    """Raised when a CEL expression fails parsing, validation, or type-checking."""

    status_code = 422


class CELEvaluationError(AegisException):
    """Raised when evaluation of a compiled CEL expression encounters a runtime error."""

    status_code = 422


class CELSecurityViolationError(AegisException):
    """Raised when a CEL expression attempts an unauthorized function call or variable escape."""

    status_code = 403
