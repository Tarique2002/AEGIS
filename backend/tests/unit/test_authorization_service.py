"""Unit tests for AuthorizationService."""

import uuid

import pytest
from app.authz.schemas import PolicyCreate, PolicyEffect
from app.authz.service import AuthorizationService
from app.core.auth import AuthenticatedPrincipal
from app.core.errors import PermissionDeniedError, PolicyDeniedError
from app.db.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_authorization_service_require_permission_allowed(
    db_session: AsyncSession,
) -> None:
    service = AuthorizationService()
    user_id = uuid.uuid4()
    user = User(id=user_id, email="authz_service_test@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    principal = AuthenticatedPrincipal(
        user_id=user_id,
        roles=["USER"],
        scopes=["tasks:read"],
    )

    # USER role has default permission 'task:read'
    decision = await service.require_permission(
        principal=principal,
        permission="task:read",
        tenant_id=user_id,
        session=db_session,
    )
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_authorization_service_require_permission_denied(
    db_session: AsyncSession,
) -> None:
    service = AuthorizationService()
    user_id = uuid.uuid4()
    user = User(id=user_id, email="authz_service_deny@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    principal = AuthenticatedPrincipal(
        user_id=user_id,
        roles=["USER"],
        scopes=["tasks:read"],
    )

    # USER role does not have 'safety:approve'
    with pytest.raises(PermissionDeniedError):
        await service.require_permission(
            principal=principal,
            permission="safety:approve",
            tenant_id=user_id,
            session=db_session,
        )


@pytest.mark.asyncio
async def test_authorization_service_policy_denied(
    db_session: AsyncSession,
) -> None:
    service = AuthorizationService()
    user_id = uuid.uuid4()
    user = User(id=user_id, email="policy_denied_test@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    principal = AuthenticatedPrincipal(
        user_id=user_id,
        roles=["ADMIN"],
        scopes=["admin"],
    )

    # Create explicit DENY policy for tool:execute
    await service.create_policy(
        principal=principal,
        data=PolicyCreate(
            name="DenyTools",
            effect=PolicyEffect.DENY,
            permissions=["tool:execute"],
            priority=1,
        ),
        tenant_id=user_id,
        session=db_session,
    )

    with pytest.raises(PolicyDeniedError):
        await service.require_permission(
            principal=principal,
            permission="tool:execute",
            tenant_id=user_id,
            session=db_session,
        )
