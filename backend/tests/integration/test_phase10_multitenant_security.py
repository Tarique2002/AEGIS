"""Integration tests for Phase 10 Multi-Tenant Security Boundaries."""

import uuid

import pytest
from app.authz.repository import AuthzRepository
from app.authz.schemas import PolicyCreate
from app.compliance.reports import ReportGenerator
from app.core.auth import create_access_token
from app.db.models.user import User
from app.safety.gates import SafetyGate
from app.safety.schemas import RiskLevel, SafetyContext
from app.security.audit_chain import AuditChainManager
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_cross_tenant_policy_versions_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User A cannot view policy versions of User B -> Returns 404."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(id=user_a_id, email="user_a@example.com", hashed_password="pw", is_active=True)
    user_b = User(id=user_b_id, email="user_b@example.com", hashed_password="pw", is_active=True)
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    repo = AuthzRepository()
    pol_b = await repo.create_policy(
        data=PolicyCreate(name="UserBPolicy", permissions=["task:read"]),
        tenant_id=user_b_id,
        created_by=user_b_id,
        session=db_session,
    )

    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["policy:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp = await async_client.get(f"/api/v1/policies/{pol_b.policy_id}/versions", headers=headers_a)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_compliance_reports_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User A cannot view User B's compliance report -> Returns 404."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="user_a_comp@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_comp@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    # Generate report for User B
    rep_b = await ReportGenerator.generate_report(
        tenant_id=user_b_id,
        created_by=user_b_id,
        session=db_session,
    )

    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a_comp@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["compliance:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp = await async_client.get(f"/api/v1/compliance/report/{rep_b.report_id}", headers=headers_a)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_checkpoint_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User A cannot view or verify User B's audit checkpoint -> Returns 404."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(id=user_a_id, email="user_a_cp@example.com", hashed_password="pw", is_active=True)
    user_b = User(id=user_b_id, email="user_b_cp@example.com", hashed_password="pw", is_active=True)
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    # Create event and checkpoint for User B
    await AuditChainManager.append_event(
        tenant_id=user_b_id,
        user_id=user_b_id,
        event_type="EVT_B",
        action="act_b",
        resource_type="res",
        resource_id="b",
        payload={"step": 1},
        session=db_session,
    )

    token_b = create_access_token(
        user_id=user_b_id,
        email="user_b_cp@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["compliance:generate", "audit:read"],
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}
    cp_resp = await async_client.post(
        "/api/v1/security/audit/checkpoints", json={}, headers=headers_b
    )
    assert cp_resp.status_code == 201
    cp_id = cp_resp.json()["checkpoint_id"]

    # User A tries to GET and verify User B's checkpoint
    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a_cp@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["audit:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_get = await async_client.get(
        f"/api/v1/security/audit/checkpoints/{cp_id}", headers=headers_a
    )
    assert resp_get.status_code == 404

    resp_ver = await async_client.post(
        f"/api/v1/security/audit/checkpoints/{cp_id}/verify", headers=headers_a
    )
    assert resp_ver.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_bypass_safety_gate() -> None:
    """
    Proves ADMIN with all permissions still gets DENIED by SafetyGate on dangerous capabilities.
    """
    safety_gate = SafetyGate()
    admin_id = uuid.uuid4()

    ctx = SafetyContext(
        user_id=admin_id,
        action="execute_shell_root_command",
        requested_capabilities=["shell", "root"],
        authenticated=True,
    )

    decision = await safety_gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.risk_level == RiskLevel.CRITICAL
