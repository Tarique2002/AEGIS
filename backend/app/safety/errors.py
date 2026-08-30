"""Domain exceptions for Phase 8 Safety Gates, Approvals, and Platform Hardening."""

from app.core.errors import (
    ApprovalExpiredError,
    ApprovalRequiredError,
    AuthorizationDeniedError,
    CircuitOpenError,
    RateLimitExceededError,
    RiskAssessmentError,
    SafetyError,
    SafetyPolicyViolationError,
    SafetyStoppedError,
    TokenRevokedError,
)

__all__ = [
    "SafetyError",
    "SafetyPolicyViolationError",
    "RiskAssessmentError",
    "ApprovalRequiredError",
    "ApprovalExpiredError",
    "TokenRevokedError",
    "RateLimitExceededError",
    "SafetyStoppedError",
    "CircuitOpenError",
    "AuthorizationDeniedError",
]
