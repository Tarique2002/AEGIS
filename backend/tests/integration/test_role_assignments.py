"""Integration tests for Role Assignments REST API."""

import uuid

import pytest
from app.authz.repository import AuthzRepository
from app.authz.schemas import RoleCreate
from app.core.auth import create_access_token
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_role_assignments_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()

    admin = User(
        id=admin_id, email="admin_assigner@example.com", hashed_password="pw", is_active=True
    )
    target = User(
        id=target_id, email="target_assignee@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([admin, target])
    await db_session.commit()

    repo = AuthzRepository()
    custom_role = await repo.create_role(
        RoleCreate(name="ORCHESTRATION_SPECIALIST", permissions=["orchestration:*"]),
        tenant_id=admin_id,
        session=db_session,
    )

    token = create_access_token(
        user_id=admin_id,
        email="admin_assigner@example.com",
        roles=["ADMIN"],
        scopes=["admin", "policy:write", "role:manage"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create role assignment
    payload = {
        "user_id": str(target_id),
        "role_id": str(custom_role.role_id),
        "enabled": True,
    }
    resp = await async_client.post("/api/v1/role-assignments", json=payload, headers=headers)
    assert resp.status_code == 201
    assign_data = resp.json()
    assignment_id = assign_data["assignment_id"]

    # 2. List role assignments
    resp = await async_client.get("/api/v1/role-assignments", headers=headers)
    assert resp.status_code == 200
    assert any(a["assignment_id"] == assignment_id for a in resp.json())

    # 3. Delete role assignment
    resp = await async_client.delete(f"/api/v1/role-assignments/{assignment_id}", headers=headers)
    assert resp.status_code == 204
