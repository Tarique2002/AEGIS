"""Integration tests for Signed Audit Checkpoint REST API."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from app.security.audit_chain import AuditChainManager
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_checkpoint_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="checkpoint_api@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="checkpoint_api@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["audit:read", "compliance:generate"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Append 2 events
    await AuditChainManager.append_event(
        tenant_id=user_id,
        user_id=user_id,
        event_type="EVT_1",
        action="act_1",
        resource_type="res",
        resource_id="1",
        payload={"step": 1},
        session=db_session,
    )
    await AuditChainManager.append_event(
        tenant_id=user_id,
        user_id=user_id,
        event_type="EVT_2",
        action="act_2",
        resource_type="res",
        resource_id="2",
        payload={"step": 2},
        session=db_session,
    )

    # 1. POST /api/v1/security/audit/checkpoints
    cp_resp = await async_client.post(
        "/api/v1/security/audit/checkpoints",
        json={},
        headers=headers,
    )
    assert cp_resp.status_code == 201
    cp_data = cp_resp.json()
    checkpoint_id = cp_data["checkpoint_id"]
    assert cp_data["verification_status"] == "VALID"
    assert len(cp_data["signature"]) > 0

    # 2. GET /api/v1/security/audit/checkpoints
    list_resp = await async_client.get("/api/v1/security/audit/checkpoints", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 3. POST /api/v1/security/audit/checkpoints/{id}/verify
    ver_resp = await async_client.post(
        f"/api/v1/security/audit/checkpoints/{checkpoint_id}/verify",
        headers=headers,
    )
    assert ver_resp.status_code == 200
    assert ver_resp.json()["valid"] is True
    assert ver_resp.json()["signature_valid"] is True
