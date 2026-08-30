"""Unit tests for Canonical Permission Registry and Permission Matching."""

from app.authz.permissions import (
    ALL_PERMISSIONS,
    Permission,
    is_permission_matching,
)


def test_canonical_permissions_defined() -> None:
    assert len(ALL_PERMISSIONS) >= 15
    assert Permission.TASK_READ.value in ALL_PERMISSIONS
    assert Permission.TOOL_EXECUTE.value in ALL_PERMISSIONS
    assert Permission.MEMORY_WRITE.value in ALL_PERMISSIONS
    assert Permission.POLICY_WRITE.value in ALL_PERMISSIONS
    assert Permission.ADMIN_ALL.value in ALL_PERMISSIONS


def test_permission_exact_matching() -> None:
    assert is_permission_matching("task:read", "task:read") is True
    assert is_permission_matching("task:read", "task:create") is False
    assert is_permission_matching("memory:write", "memory:read") is False


def test_permission_wildcard_matching() -> None:
    # admin:* matches everything
    assert is_permission_matching("task:read", "admin:*") is True
    assert is_permission_matching("memory:delete", "admin:*") is True
    assert is_permission_matching("policy:write", "*") is True

    # prefix:* matches prefix namespace
    assert is_permission_matching("task:read", "task:*") is True
    assert is_permission_matching("task:cancel", "task:*") is True
    assert is_permission_matching("memory:read", "task:*") is False
