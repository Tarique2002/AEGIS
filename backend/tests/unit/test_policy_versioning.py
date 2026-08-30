"""Unit tests for immutable PolicyVersion history in repository."""

import uuid

import pytest
from app.authz.repository import AuthzRepository
from app.authz.schemas import PolicyCreate, PolicyUpdate
from app.db.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_policy_version_lifecycle(db_session: AsyncSession) -> None:
    repo = AuthzRepository()
    tenant_id = uuid.uuid4()
    user = User(id=tenant_id, email="policy_vers@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    # 1. Create policy (v1.0.0)
    created = await repo.create_policy(
        data=PolicyCreate(name="VersionTestPol", permissions=["task:read"]),
        tenant_id=tenant_id,
        created_by=tenant_id,
        session=db_session,
    )
    assert created.version == "1.0.0"

    # 2. Update policy -> bumps to 1.0.1
    updated = await repo.update_policy(
        policy_id=created.policy_id,
        data=PolicyUpdate(description="Updated description", change_reason="Added description"),
        tenant_id=tenant_id,
        session=db_session,
        updated_by=tenant_id,
    )
    assert updated.version == "1.0.1"

    # 3. List versions
    versions = await repo.list_policy_versions(created.policy_id, tenant_id, db_session)
    assert len(versions) == 2
    version_strings = [v.version for v in versions]
    assert "1.0.0" in version_strings
    assert "1.0.1" in version_strings
