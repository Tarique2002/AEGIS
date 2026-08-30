"""Unit tests for ABACEvaluator rule evaluation."""

import uuid

import pytest
from app.authz.abac.context import AuthorizationContext
from app.authz.abac.evaluator import ABACEvaluator
from app.authz.abac.policies import ABACPolicyRule
from app.authz.schemas import PolicyEffect
from app.core.auth import AuthenticatedPrincipal


@pytest.mark.asyncio
async def test_abac_evaluator_dictionary_conditions() -> None:
    evaluator = ABACEvaluator()
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    principal = AuthenticatedPrincipal(user_id=user_id, roles=["USER"])

    ctx = AuthorizationContext.build(
        principal=principal,
        action="task:read",
        tenant_id=tenant_id,
        resource_type="task",
        resource_sensitivity="internal",
    )

    # Rule requiring sensitivity == "internal"
    rule_matching = ABACPolicyRule(
        tenant_id=tenant_id,
        name="AllowInternal",
        effect=PolicyEffect.ALLOW,
        conditions={"resource.sensitivity": "internal"},
        enabled=True,
    )
    assert evaluator.evaluate_rule(rule_matching, ctx) is True

    # Rule requiring sensitivity == "critical"
    rule_non_matching = ABACPolicyRule(
        tenant_id=tenant_id,
        name="AllowCritical",
        effect=PolicyEffect.ALLOW,
        conditions={"resource.sensitivity": "critical"},
        enabled=True,
    )
    assert evaluator.evaluate_rule(rule_non_matching, ctx) is False


@pytest.mark.asyncio
async def test_abac_evaluator_cel_expression() -> None:
    evaluator = ABACEvaluator()
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    principal = AuthenticatedPrincipal(
        user_id=user_id,
        roles=["RESEARCHER"],
        scopes=["memory:read"],
    )

    ctx = AuthorizationContext.build(
        principal=principal,
        action="memory:read",
        tenant_id=tenant_id,
        resource_type="memory",
        resource_sensitivity="internal",
        effective_roles=["RESEARCHER"],
        effective_permissions=["memory:read"],
    )

    # CEL rule: "RESEARCHER" in subject.roles && resource.sensitivity != "top_secret"
    rule = ABACPolicyRule(
        tenant_id=tenant_id,
        name="AllowResearcherNonSecret",
        effect=PolicyEffect.ALLOW,
        cel_expression="'RESEARCHER' in subject.roles && resource.sensitivity != 'top_secret'",
        enabled=True,
    )
    assert evaluator.evaluate_rule(rule, ctx) is True
