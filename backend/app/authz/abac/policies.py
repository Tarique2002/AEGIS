"""ABAC Policy schemas and rule definitions."""

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.authz.schemas import PolicyEffect


class PolicyType(str, Enum):
    """Classification of authorization policy engine."""

    RBAC = "RBAC"
    ABAC = "ABAC"
    COMBINED = "COMBINED"


class ABACPolicyRule(BaseModel):
    """Strongly typed ABAC / CEL Policy Definition."""

    policy_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    name: str
    version: str = "1.0.0"
    policy_type: PolicyType = PolicyType.COMBINED
    effect: PolicyEffect = PolicyEffect.ALLOW
    priority: int = 100
    cel_expression: str | None = None
    permissions: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
