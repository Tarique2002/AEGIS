"""Integration tests for ABAC Policy creation, validation, and CEL expressions via REST API."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_abac_policy_api_validate_and_create(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="abac_api@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="abac_api@example.com",
        roles=["ADMIN"],
        scopes=["policy:read", "policy:write"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Validate CEL policy
    val_resp = await async_client.post(
        "/api/v1/policies/validate",
        json={"cel_expression": "subject.tenant_id == resource.tenant_id"},
        headers=headers,
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True

    # 2. Create ABAC policy with CEL expression
    create_resp = await async_client.post(
        "/api/v1/policies",
        json={
            "name": "TenantIsolationCEL",
            "policy_type": "ABAC",
            "effect": "ALLOW",
            "priority": 50,
            "permissions": ["task:read"],
            "cel_expression": "subject.tenant_id == resource.tenant_id",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    pol_id = create_resp.json()["policy_id"]
    assert create_resp.json()["cel_expression"] == "subject.tenant_id == resource.tenant_id"

    # 3. Check version history
    ver_resp = await async_client.get(f"/api/v1/policies/{pol_id}/versions", headers=headers)
    assert ver_resp.status_code == 200
    assert len(ver_resp.json()) >= 1
