"""Comprehensive Security & Multi-Tenant Isolation Tests for Phase 9 (Scenarios A through G)."""

import uuid

import pytest
from app.authz.policy import PolicyEngine
from app.authz.repository import AuthzRepository
from app.authz.schemas import PolicyCreate, PolicyDefinition, PolicyEffect
from app.core.auth import create_access_token
from app.db.models.user import User
from app.safety.gates import SafetyGate
from app.safety.schemas import RiskLevel, SafetyContext
from app.security.audit_chain import AuditChainManager, AuditChainVerifier
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_scenario_a_privilege_escalation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Scenario A: User attempts to assign themselves an ADMIN role -> Rejected."""
    user_id = uuid.uuid4()
    user = User(id=user_id, email="attacker@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="attacker@example.com",
        roles=["USER"],
        scopes=["tasks:read"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "user_id": str(user_id),
        "role_id": str(uuid.uuid4()),
        "enabled": True,
    }
    # Unprivileged user lacks role:manage permission and policy:write scope
    resp = await async_client.post("/api/v1/role-assignments", json=payload, headers=headers)
    assert resp.status_code in [403, 422]


@pytest.mark.asyncio
async def test_scenario_b_cross_tenant_policy_access(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Scenario B: User A requests User B's policy -> Returns 404."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(id=user_a_id, email="usera@example.com", hashed_password="pw", is_active=True)
    user_b = User(id=user_b_id, email="userb@example.com", hashed_password="pw", is_active=True)
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    # User B creates a policy
    repo = AuthzRepository()
    policy_b = await repo.create_policy(
        PolicyCreate(name="UserBPolicy", permissions=["task:read"]),
        tenant_id=user_b_id,
        created_by=user_b_id,
        session=db_session,
    )

    # User A tries to GET User B's policy
    token_a = create_access_token(
        user_id=user_a_id,
        email="usera@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["policy:read"],
    )
    headers = {"Authorization": f"Bearer {token_a}"}

    resp = await async_client.get(f"/api/v1/policies/{policy_b.policy_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scenario_c_scope_spoofing(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Scenario C: Request attempts header-based scope spoofing -> Ignored and 403."""
    user_id = uuid.uuid4()
    user = User(id=user_id, email="spoof_user@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    # Token has only tasks:read scope
    token = create_access_token(
        user_id=user_id,
        email="spoof_user@example.com",
        roles=["USER"],
        scopes=["tasks:read"],
    )
    # Attempt to spoof admin scope via custom headers
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Scopes": "admin,policy:write",
        "X-User-Role": "ADMIN",
    }

    # Attempt to create a policy which requires policy:write scope
    resp = await async_client.post(
        "/api/v1/policies",
        json={"name": "SpoofedPolicy", "permissions": ["task:read"]},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_scenario_d_admin_safety_bypass_forbidden() -> None:
    """Scenario D: ADMIN attempts a CRITICAL / forbidden capability -> SafetyGate DENIES."""
    safety_gate = SafetyGate()
    admin_id = uuid.uuid4()

    # SafetyContext with requested forbidden capability
    ctx = SafetyContext(
        user_id=admin_id,
        action="execute_shell_root_command",
        requested_capabilities=["shell", "root"],
        authenticated=True,
    )

    decision = await safety_gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.risk_level == RiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_scenario_e_audit_tampering_detection(
    db_session: AsyncSession,
) -> None:
    """Scenario E: Modifying a persisted event payload -> AuditChainVerifier detects tampering."""
    tenant_id = uuid.uuid4()
    user = User(
        id=tenant_id, email="tamper_detect@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    event = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="PAYMENT_PROCESSED",
        action="process_payment",
        resource_type="payment",
        resource_id="pay-101",
        payload={"amount": 500, "currency": "USD"},
        session=db_session,
    )

    # Tamper with the recorded payload
    event.audit_metadata = {"amount": 5000000, "currency": "USD"}
    await db_session.flush()

    verification = await AuditChainVerifier.verify_tenant_chain(tenant_id, db_session)
    assert verification.valid is False
    assert "Payload tampering detected" in (verification.failure_reason or "")


@pytest.mark.asyncio
async def test_scenario_f_audit_deletion_detection(
    db_session: AsyncSession,
) -> None:
    """Scenario F: Deleting an event in the chain -> Verification detects broken sequence/chain."""
    tenant_id = uuid.uuid4()
    user = User(
        id=tenant_id, email="delete_detect@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="EVENT_1",
        action="action_1",
        resource_type="res",
        resource_id="1",
        payload={"step": 1},
        session=db_session,
    )
    event2 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="EVENT_2",
        action="action_2",
        resource_type="res",
        resource_id="2",
        payload={"step": 2},
        session=db_session,
    )
    await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="EVENT_3",
        action="action_3",
        resource_type="res",
        resource_id="3",
        payload={"step": 3},
        session=db_session,
    )

    # Delete event2 in the middle
    await db_session.delete(event2)
    await db_session.flush()

    verification = await AuditChainVerifier.verify_tenant_chain(tenant_id, db_session)
    assert verification.valid is False
    assert "Sequence gap" in (verification.failure_reason or "") or "Broken chain" in (
        verification.failure_reason or ""
    )


@pytest.mark.asyncio
async def test_scenario_g_explicit_deny_precedence() -> None:
    """Scenario G: Role has permission tool:execute, Policy explicitly denies -> DENY."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    deny_policy = PolicyDefinition(
        name="StrictToolDeny",
        tenant_id=tenant_id,
        priority=1,
        effect=PolicyEffect.DENY,
        permissions=["tool:execute"],
    )

    decision = PolicyEngine.evaluate_policies(
        permission="tool:execute",
        user_id=user_id,
        tenant_id=tenant_id,
        policies=[deny_policy],
        role_permissions=["tool:execute", "admin:*"],  # Even admin:* permission
    )

    assert decision.allowed is False
    assert "explicitly DENIED" in decision.reason
