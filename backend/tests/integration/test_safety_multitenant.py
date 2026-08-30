"""Integration tests for Multi-Tenant isolation in safety audits and approvals."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_cross_tenant_approval_isolation_returns_404(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(id=user_a_id, email="tenant_a@example.com", hashed_password="pw", is_active=True)
    user_b = User(id=user_b_id, email="tenant_b@example.com", hashed_password="pw", is_active=True)
    db_session.add(user_a)
    db_session.add(user_b)
    await db_session.commit()

    token_a = create_access_token(user_id=user_a_id)
    token_b = create_access_token(user_id=user_b_id)

    # 1. User A creates an approval request
    payload = {
        "action": "confidential_op",
        "resource": "resource_a",
        "risk_level": "HIGH",
        "reason": "Tenant A operation",
    }
    resp = await async_client.post(
        "/api/v1/safety/approvals",
        json=payload,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201
    approval_id = resp.json()["approval_id"]

    # 2. User B attempts to access User A's approval -> must return 404 Not Found
    resp_b_get = await async_client.get(
        f"/api/v1/safety/approvals/{approval_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b_get.status_code == 404

    # 3. User B attempts to approve User A's approval -> must return 404 Not Found
    resp_b_approve = await async_client.post(
        f"/api/v1/safety/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b_approve.status_code == 404
