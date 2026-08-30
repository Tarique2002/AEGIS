"""Unit tests for ABAC AuthorizationContext construction and serialization."""

import uuid

import pytest
from app.authz.abac.context import AuthorizationContext
from app.core.auth import AuthenticatedPrincipal


@pytest.mark.asyncio
async def test_abac_context_build() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    principal = AuthenticatedPrincipal(
        user_id=user_id,
        email="test_user@example.com",
        roles=["USER", "RESEARCHER"],
        scopes=["task:read", "task:write"],
    )

    ctx = AuthorizationContext.build(
        principal=principal,
        action="task:read",
        tenant_id=tenant_id,
        resource_type="task",
        resource_id="task-456",
        resource_owner_id=str(user_id),
        resource_sensitivity="confidential",
        resource_risk_level="MEDIUM",
        effective_roles=["USER", "RESEARCHER"],
        effective_permissions=["task:read"],
        request_params={"filter": "all"},
    )

    assert ctx.subject.user_id == str(user_id)
    assert ctx.subject.tenant_id == str(tenant_id)
    assert ctx.subject.roles == ["USER", "RESEARCHER"]
    assert ctx.resource.resource_type == "task"
    assert ctx.resource.sensitivity == "confidential"
    assert ctx.resource.risk_level == "MEDIUM"
    assert ctx.request.action == "task:read"

    eval_dict = ctx.to_eval_dict()
    assert eval_dict["subject"]["user_id"] == str(user_id)
    assert eval_dict["resource"]["sensitivity"] == "confidential"
    assert eval_dict["action"] == "task:read"
