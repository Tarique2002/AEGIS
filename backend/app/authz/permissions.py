"""Canonical Permission Registry and Permission taxonomy for AEGIS Phase 9."""

from enum import Enum


class Permission(str, Enum):
    """Canonical permission identifiers for all AEGIS platform resources and actions."""

    # Task permissions
    TASK_READ = "task:read"
    TASK_CREATE = "task:create"
    TASK_CANCEL = "task:cancel"
    TASK_RESUME = "task:resume"

    # Tool permissions
    TOOL_READ = "tool:read"
    TOOL_EXECUTE = "tool:execute"

    # Memory permissions
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"

    # Orchestration permissions
    ORCHESTRATION_READ = "orchestration:read"
    ORCHESTRATION_CREATE = "orchestration:create"
    ORCHESTRATION_CANCEL = "orchestration:cancel"

    # Safety permissions
    SAFETY_READ = "safety:read"
    SAFETY_APPROVE = "safety:approve"
    SAFETY_AUDIT = "safety:audit"

    # Policy permissions
    POLICY_READ = "policy:read"
    POLICY_WRITE = "policy:write"

    # User & Role permissions
    USER_READ = "user:read"
    USER_MANAGE = "user:manage"
    ROLE_READ = "role:read"
    ROLE_MANAGE = "role:manage"

    # Token & Session permissions
    TOKEN_REVOKE = "token:revoke"

    # Administrative wildcard
    ADMIN_ALL = "admin:*"


ALL_PERMISSIONS: set[str] = {p.value for p in Permission}


def is_permission_matching(required: str, granted: str) -> bool:
    """
    Check if a granted permission satisfies the required permission.
    Supports wildcards like 'admin:*' or 'task:*'.
    """
    if granted == "admin:*" or granted == "*":
        return True
    if granted == required:
        return True
    if granted.endswith(":*"):
        prefix = granted[:-2]
        return required.startswith(f"{prefix}:")
    return False
