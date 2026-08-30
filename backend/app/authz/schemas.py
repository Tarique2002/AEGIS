"""Strongly typed schemas and contracts for Phase 9 Dynamic Authorization & RBAC."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class TokenScope(str, Enum):
    """Canonical OAuth2 and JWT permission scopes."""

    TASKS_READ = "tasks:read"
    TASKS_WRITE = "tasks:write"
    TOOLS_READ = "tools:read"
    TOOLS_EXECUTE = "tools:execute"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    ORCHESTRATION_READ = "orchestration:read"
    ORCHESTRATION_WRITE = "orchestration:write"
    SAFETY_READ = "safety:read"
    SAFETY_APPROVE = "safety:approve"
    AUDIT_READ = "audit:read"
    POLICY_READ = "policy:read"
    POLICY_WRITE = "policy:write"
    ADMIN = "admin"


class PolicyEffect(str, Enum):
    """Effect of dynamic authorization policy rule."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class Role(AegisBaseSchema):
    """Role definition with associated permissions."""

    role_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    tenant_id: uuid.UUID | None = None
    is_system_role: bool = False
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RoleCreate(AegisBaseSchema):
    """Request payload to create a custom role."""

    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    enabled: bool = True


class RoleUpdate(AegisBaseSchema):
    """Request payload to modify an existing custom role."""

    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None
    enabled: bool | None = None


class UserRoleAssignment(AegisBaseSchema):
    """Tenant-scoped role assignment linking user to role."""

    assignment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    role_id: uuid.UUID
    tenant_id: uuid.UUID
    assigned_by: uuid.UUID | None = None
    expires_at: datetime | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UserRoleAssignmentCreate(AegisBaseSchema):
    """Request payload to assign a role to a user."""

    user_id: uuid.UUID
    role_id: uuid.UUID
    expires_at: datetime | None = None
    enabled: bool = True


class PolicyDefinition(AegisBaseSchema):
    """Dynamic tenant authorization policy rule."""

    policy_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(..., min_length=2, max_length=100)
    version: str = "1.0.0"
    description: str | None = None
    tenant_id: uuid.UUID
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=1000)
    effect: PolicyEffect = PolicyEffect.ALLOW
    policy_type: str = "COMBINED"
    permissions: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    cel_expression: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PolicyCreate(AegisBaseSchema):
    """Request payload to create a dynamic policy rule."""

    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    priority: int = Field(default=100, ge=1, le=1000)
    effect: PolicyEffect = PolicyEffect.ALLOW
    policy_type: str = "COMBINED"
    permissions: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    cel_expression: str | None = None
    enabled: bool = True


class PolicyUpdate(AegisBaseSchema):
    """Request payload to modify a dynamic policy rule."""

    name: str | None = None
    description: str | None = None
    priority: int | None = None
    effect: PolicyEffect | None = None
    policy_type: str | None = None
    permissions: list[str] | None = None
    conditions: dict[str, Any] | None = None
    cel_expression: str | None = None
    change_reason: str | None = None
    enabled: bool | None = None


class PolicyValidationRequest(AegisBaseSchema):
    """Request to validate a policy without saving."""

    cel_expression: str | None = None
    permissions: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)


class PolicyValidationResponse(AegisBaseSchema):
    """Result of policy validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PolicySimulationRequest(AegisBaseSchema):
    """Request payload to simulate policy evaluation on sample context."""

    permission: str
    resource_type: str
    resource_id: str | None = None
    resource_owner_id: str | None = None
    resource_sensitivity: str = "internal"
    resource_risk_level: str = "LOW"
    action: str = "read"
    request_params: dict[str, Any] = Field(default_factory=dict)


class PolicySimulationResponse(AegisBaseSchema):
    """Simulated policy decision result."""

    allowed: bool
    reason: str
    matched_policy_id: uuid.UUID | None = None
    matched_policy_name: str | None = None
    policy_type: str | None = None
    policy_version: str | None = None
    matched_role: str | None = None
    simulated_at: datetime = Field(default_factory=utc_now)


class PolicyVersion(AegisBaseSchema):
    """Historical version record for an authorization policy."""

    version_id: uuid.UUID
    policy_id: uuid.UUID
    tenant_id: uuid.UUID
    version: str
    name: str
    policy_type: str
    effect: PolicyEffect
    priority: int
    permissions: list[str]
    conditions: dict[str, Any]
    cel_expression: str | None = None
    change_reason: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class AuthorizationDecision(AegisBaseSchema):
    """Structured result of dynamic RBAC, ABAC & policy evaluation."""

    decision_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    allowed: bool
    permission: str
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    action: str = ""
    resource_type: str = ""
    resource_id: str | None = None
    matched_policy_id: uuid.UUID | None = None
    matched_policy_ids: list[uuid.UUID] = Field(default_factory=list)
    matched_role: str | None = None
    matched_roles: list[str] = Field(default_factory=list)
    matched_scopes: list[str] = Field(default_factory=list)
    reason: str
    decision_reason: str | None = None
    policy_version: str = "1.0.0"
    policy_versions: list[str] = Field(default_factory=list)
    evaluation_duration_ms: float = 0.0
    evaluated_at: datetime = Field(default_factory=utc_now)


class EffectiveAuthorizationResponse(AegisBaseSchema):
    """Effective authorization context for caller."""

    user_id: uuid.UUID
    roles: list[str]
    permissions: list[str]
    scopes: list[str]
    is_authenticated: bool = True
