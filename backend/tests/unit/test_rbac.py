"""Unit tests for Dynamic RBAC and System Roles."""

import uuid
from datetime import timedelta

import pytest
from app.authz.repository import AuthzRepository
from app.authz.roles import DEFAULT_ROLE_PERMISSIONS, SystemRole
from app.authz.schemas import (
    RoleCreate,
    UserRoleAssignmentCreate,
)
from app.core.errors import RoleAssignmentError
from app.db.models.user import User
from app.schemas.common import utc_now
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_system_roles_default_permissions() -> None:
    assert SystemRole.VIEWER.value in DEFAULT_ROLE_PERMISSIONS
    assert "task:read" in DEFAULT_ROLE_PERMISSIONS[SystemRole.VIEWER.value]
    assert "task:create" not in DEFAULT_ROLE_PERMISSIONS[SystemRole.VIEWER.value]

    assert SystemRole.ADMIN.value in DEFAULT_ROLE_PERMISSIONS
    assert "admin:*" in DEFAULT_ROLE_PERMISSIONS[SystemRole.ADMIN.value]


@pytest.mark.asyncio
async def test_custom_role_crud(db_session: AsyncSession) -> None:
    repo = AuthzRepository()
    tenant_id = uuid.uuid4()
    user = User(id=tenant_id, email="tenant_role_test@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    # Create role
    create_req = RoleCreate(
        name="CUSTOM_ANALYST",
        description="Data analyst role",
        permissions=["task:read", "memory:read"],
    )
    role = await repo.create_role(create_req, tenant_id, db_session)
    assert role.name == "CUSTOM_ANALYST"
    assert role.tenant_id == tenant_id
    assert role.is_system_role is False

    # List roles
    roles = await repo.list_roles(tenant_id, db_session)
    assert any(r.name == "CUSTOM_ANALYST" for r in roles)

    # Delete role
    await repo.delete_role(role.role_id, tenant_id, db_session)
    deleted = await repo.get_role(role.role_id, tenant_id, db_session)
    assert deleted is None


@pytest.mark.asyncio
async def test_role_assignment_and_expiration(db_session: AsyncSession) -> None:
    repo = AuthzRepository()
    tenant_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    target_user_id = uuid.uuid4()

    tenant_user = User(id=tenant_id, email="tenant_admin@example.com", hashed_password="pw")
    admin_user = User(id=admin_id, email="admin_assigner@example.com", hashed_password="pw")
    target_user = User(id=target_user_id, email="target_user@example.com", hashed_password="pw")
    db_session.add_all([tenant_user, admin_user, target_user])
    await db_session.commit()

    # Create custom role
    role = await repo.create_role(
        RoleCreate(name="MEMORY_SUPERUSER", permissions=["memory:*"]),
        tenant_id,
        db_session,
    )

    # Assign role to target user
    assignment = await repo.create_role_assignment(
        UserRoleAssignmentCreate(
            user_id=target_user_id,
            role_id=role.role_id,
            expires_at=utc_now() + timedelta(hours=1),
        ),
        tenant_id=tenant_id,
        assigned_by=admin_id,
        session=db_session,
    )
    assert assignment.user_id == target_user_id

    # Check effective permissions
    roles, perms = await repo.get_user_effective_roles_and_permissions(
        user_id=target_user_id,
        tenant_id=tenant_id,
        session=db_session,
    )
    assert "MEMORY_SUPERUSER" in roles
    assert "memory:*" in perms


@pytest.mark.asyncio
async def test_prevent_self_role_assignment_escalation(db_session: AsyncSession) -> None:
    repo = AuthzRepository()
    user_id = uuid.uuid4()
    role_id = uuid.uuid4()

    with pytest.raises(RoleAssignmentError):
        await repo.create_role_assignment(
            UserRoleAssignmentCreate(user_id=user_id, role_id=role_id),
            tenant_id=user_id,
            assigned_by=user_id,  # same user assigning to self
            session=db_session,
        )
