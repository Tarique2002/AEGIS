"""Unit tests for deterministic PolicyEngine precedence."""

import uuid

import pytest
from app.authz.abac.context import AuthorizationContext
from app.authz.policy import PolicyEngine
from app.authz.schemas import PolicyDefinition, PolicyEffect
from app.core.auth import AuthenticatedPrincipal


@pytest.mark.asyncio
async def test_explicit_deny_precedence_over_role() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    principal = AuthenticatedPrincipal(user_id=user_id, roles=["ADMIN"])

    ctx = AuthorizationContext.build(
        principal=principal,
        action="tool:execute",
        tenant_id=tenant_id,
        resource_type="tool",
    )

    # DENY policy for tool:execute
    deny_pol = PolicyDefinition(
        tenant_id=tenant_id,
        name="DenyAllTools",
        effect=PolicyEffect.DENY,
        priority=1,
        permissions=["tool:execute"],
        enabled=True,
    )

    decision = PolicyEngine.evaluate_policies(
        permission="tool:execute",
        user_id=user_id,
        tenant_id=tenant_id,
        policies=[deny_pol],
        role_permissions=["tool:*", "admin:*"],
        context=ctx,
    )

    assert decision.allowed is False
    assert decision.matched_policy_id == deny_pol.policy_id
    assert "explicitly DENIED" in decision.reason


@pytest.mark.asyncio
async def test_abac_cel_allow_precedence() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    principal = AuthenticatedPrincipal(user_id=user_id, roles=["RESEARCHER"])

    ctx = AuthorizationContext.build(
        principal=principal,
        action="memory:read",
        tenant_id=tenant_id,
        resource_type="memory",
        resource_sensitivity="public",
    )

    # ABAC ALLOW policy with CEL expression
    abac_pol = PolicyDefinition(
        tenant_id=tenant_id,
        name="AllowPublicMemory",
        effect=PolicyEffect.ALLOW,
        priority=10,
        permissions=["memory:read"],
        cel_expression="resource.sensitivity == 'public'",
        enabled=True,
    )

    decision = PolicyEngine.evaluate_policies(
        permission="memory:read",
        user_id=user_id,
        tenant_id=tenant_id,
        policies=[abac_pol],
        role_permissions=[],
        context=ctx,
    )

    assert decision.allowed is True
    assert decision.matched_policy_id == abac_pol.policy_id
