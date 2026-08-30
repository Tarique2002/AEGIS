"""Unit tests for PolicyEngine deterministic precedence and evaluation."""

import uuid

from app.authz.policy import PolicyEngine
from app.authz.schemas import PolicyDefinition, PolicyEffect


def test_policy_engine_explicit_deny_precedence() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # User has assigned role permission for tool:execute
    role_perms = ["tool:execute", "task:read"]

    # But tenant policy explicitly DENIES tool:execute with priority 10
    deny_policy = PolicyDefinition(
        name="BlockExternalTools",
        tenant_id=tenant_id,
        priority=10,
        effect=PolicyEffect.DENY,
        permissions=["tool:execute"],
    )

    decision = PolicyEngine.evaluate_policies(
        permission="tool:execute",
        user_id=user_id,
        tenant_id=tenant_id,
        policies=[deny_policy],
        role_permissions=role_perms,
    )

    assert decision.allowed is False
    assert "explicitly DENIED" in decision.reason
    assert decision.matched_policy_id == deny_policy.policy_id


def test_policy_engine_explicit_allow() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    allow_policy = PolicyDefinition(
        name="AllowTaskManagement",
        tenant_id=tenant_id,
        priority=50,
        effect=PolicyEffect.ALLOW,
        permissions=["task:*"],
    )

    decision = PolicyEngine.evaluate_policies(
        permission="task:create",
        user_id=user_id,
        tenant_id=tenant_id,
        policies=[allow_policy],
        role_permissions=[],
    )

    assert decision.allowed is True
    assert "permitted by policy" in decision.reason


def test_policy_engine_default_deny() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    decision = PolicyEngine.evaluate_policies(
        permission="safety:approve",
        user_id=user_id,
        tenant_id=tenant_id,
        policies=[],
        role_permissions=["task:read"],
    )

    assert decision.allowed is False
    assert "Default DENY" in decision.reason
