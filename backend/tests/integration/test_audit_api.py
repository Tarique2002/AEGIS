"""Integration tests for Cryptographic Audit REST API and Verification."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from app.security.audit_chain import AuditChainManager
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_audit_api_and_verification(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    sec_admin_id = uuid.uuid4()
    sec_admin = User(
        id=sec_admin_id,
        email="sec_admin@example.com",
        hashed_password="pw",
        is_active=True,
    )
    db_session.add(sec_admin)
    await db_session.commit()

    token = create_access_token(
        user_id=sec_admin_id,
        email="sec_admin@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["audit:read", "safety:audit"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Append test audit events in chain
    await AuditChainManager.append_event(
        tenant_id=sec_admin_id,
        user_id=sec_admin_id,
        event_type="TASK_DISPATCHED",
        action="dispatch_task",
        resource_type="task",
        resource_id="task-123",
        payload={"task_name": "Audit Test Task"},
        session=db_session,
    )

    # 1. GET /api/v1/security/audit
    resp = await async_client.get("/api/v1/security/audit", headers=headers)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1
    assert events[0]["tenant_id"] == str(sec_admin_id)
    assert events[0]["sequence_number"] == 1

    # 2. GET /api/v1/security/audit/verify
    resp = await async_client.get("/api/v1/security/audit/verify", headers=headers)
    assert resp.status_code == 200
    verify_data = resp.json()
    assert verify_data["valid"] is True
    assert verify_data["checked_events"] >= 1
