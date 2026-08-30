"""Integration tests for Safety API endpoints."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_safety_policy_and_status_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="safety_test@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # GET /api/v1/safety/policy
    resp = await async_client.get("/api/v1/safety/policy", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "policy_version" in data
    assert "max_risk_level" in data

    # GET /api/v1/safety/status
    resp = await async_client.get("/api/v1/safety/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_approval_lifecycle_api(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="approvals_test@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create approval request
    payload = {
        "action": "external_api_call",
        "resource": "https://api.example.com/v1/data",
        "risk_level": "HIGH",
        "reason": "Need external customer dataset",
        "metadata": {"endpoint": "/v1/data"},
    }
    resp = await async_client.post("/api/v1/safety/approvals", json=payload, headers=headers)
    assert resp.status_code == 201
    appr_data = resp.json()
    approval_id = appr_data["approval_id"]
    assert appr_data["status"] == "PENDING"

    # 2. Get approval status
    resp = await async_client.get(f"/api/v1/safety/approvals/{approval_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["approval_id"] == approval_id

    # 3. Approve action
    resp = await async_client.post(
        f"/api/v1/safety/approvals/{approval_id}/approve", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_token_revocation_endpoint(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="revoke_api@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    token_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, token_id=token_id)
    headers = {"Authorization": f"Bearer {token}"}

    # POST /api/v1/auth/revoke
    resp = await async_client.post(
        "/api/v1/auth/revoke", json={"token_id": token_id}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["revoked_token_id"] == token_id

    # Subsequent call with the revoked token must fail with 401
    resp_after = await async_client.get("/api/v1/safety/policy", headers=headers)
    assert resp_after.status_code == 401
