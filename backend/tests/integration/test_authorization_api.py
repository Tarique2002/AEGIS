"""Integration tests for Authorization REST API endpoints."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_authorization_me_and_permissions(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="auth_me_test@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="auth_me_test@example.com",
        roles=["USER"],
        scopes=["tasks:read", "tools:read"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /api/v1/authorization/me
    resp = await async_client.get("/api/v1/authorization/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(user_id)
    assert "USER" in data["roles"]
    assert "task:read" in data["permissions"]
    assert "tasks:read" in data["scopes"]

    # 2. GET /api/v1/permissions
    resp = await async_client.get("/api/v1/permissions", headers=headers)
    assert resp.status_code == 200
    perms = resp.json()
    assert "task:read" in perms
    assert "admin:*" in perms


@pytest.mark.asyncio
async def test_roles_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin_id = uuid.uuid4()
    admin = User(
        id=admin_id, email="admin_roles_test@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(admin)
    await db_session.commit()

    admin_token = create_access_token(
        user_id=admin_id,
        email="admin_roles_test@example.com",
        roles=["ADMIN"],
        scopes=["admin", "policy:write"],
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. List default roles
    resp = await async_client.get("/api/v1/roles", headers=headers)
    assert resp.status_code == 200

    # 2. Create custom role
    create_payload = {
        "name": "CUSTOM_DATA_SCIENTIST",
        "description": "Data science role",
        "permissions": ["task:read", "task:create", "memory:read"],
        "enabled": True,
    }
    resp = await async_client.post("/api/v1/roles", json=create_payload, headers=headers)
    assert resp.status_code == 201
    role_data = resp.json()
    role_id = role_data["role_id"]
    assert role_data["name"] == "CUSTOM_DATA_SCIENTIST"

    # 3. Get role
    resp = await async_client.get(f"/api/v1/roles/{role_id}", headers=headers)
    assert resp.status_code == 200

    # 4. Update role
    resp = await async_client.patch(
        f"/api/v1/roles/{role_id}",
        json={"description": "Updated description"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"

    # 5. Delete role
    resp = await async_client.delete(f"/api/v1/roles/{role_id}", headers=headers)
    assert resp.status_code == 204
