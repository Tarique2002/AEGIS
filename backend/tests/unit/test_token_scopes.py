"""Unit tests for Token Scopes, extraction, and validation."""

import uuid

import pytest
from app.authz.service import AuthorizationService
from app.core.auth import (
    AuthenticatedPrincipal,
    create_access_token,
    verify_access_token,
)
from app.core.errors import ScopeRequiredError


def test_token_scope_creation_and_verification() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(
        user_id=user_id,
        email="scoped_user@example.com",
        scopes=["tasks:read", "tasks:write", "tools:read"],
    )

    principal = verify_access_token(token)
    assert principal.user_id == user_id
    assert "tasks:read" in principal.scopes
    assert "tasks:write" in principal.scopes
    assert "tools:read" in principal.scopes
    assert "policy:write" not in principal.scopes


def test_scope_validation_success_and_failure() -> None:
    service = AuthorizationService()
    user_id = uuid.uuid4()

    principal = AuthenticatedPrincipal(
        user_id=user_id,
        scopes=["tasks:read", "memory:read"],
        roles=["user"],
    )

    # Valid scope
    assert service.check_scope(principal, "tasks:read") is True
    service.require_scope(principal, "tasks:read")

    # Missing scope
    assert service.check_scope(principal, "policy:write") is False
    with pytest.raises(ScopeRequiredError):
        service.require_scope(principal, "policy:write")


def test_admin_scope_wildcard() -> None:
    service = AuthorizationService()
    user_id = uuid.uuid4()

    admin_principal = AuthenticatedPrincipal(
        user_id=user_id,
        scopes=["admin"],
        roles=["user"],
    )

    assert service.check_scope(admin_principal, "policy:write") is True
    assert service.check_scope(admin_principal, "audit:read") is True


@pytest.mark.asyncio
async def test_issue_access_token_endpoint() -> None:
    from app.api.v1.endpoints.auth import TokenIssueRequest, issue_access_token

    req = TokenIssueRequest(
        email="operator@aegis.io",
        roles=["ADMIN", "OPERATOR"],
        scopes=["*"],
    )
    res = await issue_access_token(req)
    assert res.token_type == "bearer"
    assert res.access_token is not None
    assert res.email == "operator@aegis.io"
    assert "ADMIN" in res.roles

    # Verify the issued token can be verified
    principal = verify_access_token(res.access_token)
    assert principal.email == "operator@aegis.io"
    assert "ADMIN" in principal.roles
