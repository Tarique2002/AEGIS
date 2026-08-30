"""Integration tests for Dynamic Policy REST API endpoints."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_policy_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin_id = uuid.uuid4()
    admin = User(
        id=admin_id, email="policy_api_test@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token(
        user_id=admin_id,
        email="policy_api_test@example.com",
        roles=["ADMIN"],
        scopes=["admin", "policy:write", "policy:read"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create policy
    payload = {
        "name": "BlockDestructiveSQL",
        "description": "Block all destructive sql actions",
        "priority": 10,
        "effect": "DENY",
        "permissions": ["tool:execute"],
        "conditions": {"database": "production"},
        "enabled": True,
    }
    resp = await async_client.post("/api/v1/policies", json=payload, headers=headers)
    assert resp.status_code == 201
    p_data = resp.json()
    policy_id = p_data["policy_id"]
    assert p_data["name"] == "BlockDestructiveSQL"
    assert p_data["version"] == "1.0.0"

    # 2. Get policy
    resp = await async_client.get(f"/api/v1/policies/{policy_id}", headers=headers)
    assert resp.status_code == 200

    # 3. Update policy and verify version increment
    resp = await async_client.patch(
        f"/api/v1/policies/{policy_id}",
        json={"priority": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.0.1"

    # 4. List policies
    resp = await async_client.get("/api/v1/policies", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 5. Delete policy
    resp = await async_client.delete(f"/api/v1/policies/{policy_id}", headers=headers)
    assert resp.status_code == 204
