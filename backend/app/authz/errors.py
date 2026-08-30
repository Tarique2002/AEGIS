"""Domain exceptions for Phase 9 Dynamic Authorization, RBAC, and Token Scopes."""

from app.core.errors import (
    AuditIntegrityError,
    AuthorizationError,
    PermissionDeniedError,
    PolicyDeniedError,
    RoleAssignmentError,
    ScopeRequiredError,
)

__all__ = [
    "AuthorizationError",
    "PermissionDeniedError",
    "ScopeRequiredError",
    "PolicyDeniedError",
    "RoleAssignmentError",
    "AuditIntegrityError",
]
