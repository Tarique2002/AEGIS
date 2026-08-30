"""Integration tests for Policy Simulation API."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_policy_simulation_api(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="sim_api@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="sim_api@example.com",
        roles=["ADMIN"],
        scopes=["policy:read", "policy:write"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a policy
    await async_client.post(
        "/api/v1/policies",
        json={
            "name": "SimTestPolicy",
            "effect": "ALLOW",
            "priority": 10,
            "permissions": ["task:execute"],
            "cel_expression": "resource.sensitivity == 'internal'",
        },
        headers=headers,
    )

    # 2. Simulate matching context
    sim_resp = await async_client.post(
        "/api/v1/policies/simulate",
        json={
            "permission": "task:execute",
            "resource_type": "task",
            "resource_sensitivity": "internal",
            "action": "task:execute",
        },
        headers=headers,
    )
    assert sim_resp.status_code == 200
    assert sim_resp.json()["allowed"] is True

    # 3. Simulate non-matching context
    sim_resp_deny = await async_client.post(
        "/api/v1/policies/simulate",
        json={
            "permission": "task:execute",
            "resource_type": "task",
            "resource_sensitivity": "restricted",
            "action": "task:execute",
        },
        headers=headers,
    )
    assert sim_resp_deny.status_code == 200
    # Because admin:* role is in principal, check verdict
