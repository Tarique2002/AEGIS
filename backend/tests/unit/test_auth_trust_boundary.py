"""Unit tests for AuthenticatedPrincipal, Bearer token crypto, and AuthProviders."""

import uuid

import pytest
from app.core.auth import (
    DevelopmentAuthProvider,
    ProductionAuthProvider,
    create_access_token,
    get_auth_provider,
    verify_access_token,
)
from fastapi import HTTPException, Request


def test_create_and_verify_access_token() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, email="test@example.com", roles=["admin"])

    principal = verify_access_token(token)
    assert principal.user_id == user_id
    assert principal.email == "test@example.com"
    assert principal.roles == ["admin"]
    assert principal.is_authenticated is True
    assert principal.auth_scheme == "bearer"


def test_verify_access_token_tampered_signature() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, email="test@example.com")

    # Tamper with the payload
    parts = token.split(".")
    tampered_token = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(tampered_token)
    assert exc_info.value.status_code == 401


def test_verify_access_token_expired() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, expires_in_seconds=-10)

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_production_auth_provider_requires_bearer_token() -> None:
    provider = ProductionAuthProvider()

    # Empty request without Authorization header
    scope = {"type": "http", "headers": []}
    req = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        await provider.authenticate(req)
    assert exc_info.value.status_code == 401
    assert "Authorization header missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_production_auth_provider_authenticates_valid_token() -> None:
    provider = ProductionAuthProvider()
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, email="prod@example.com")

    headers = [(b"authorization", f"Bearer {token}".encode())]
    scope = {"type": "http", "headers": headers}
    req = Request(scope)

    principal = await provider.authenticate(req)
    assert principal.user_id == user_id
    assert principal.email == "prod@example.com"
    assert principal.auth_scheme == "bearer"


@pytest.mark.asyncio
async def test_production_auth_provider_ignores_spoofed_x_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ProductionAuthProvider()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    token_a = create_access_token(user_id=user_a, email="user_a@example.com")

    # Client presents token for User A, but attempts to spoof X-User-Id for User B
    headers = [
        (b"authorization", f"Bearer {token_a}".encode()),
        (b"x-user-id", str(user_b).encode("utf-8")),
    ]
    scope = {"type": "http", "headers": headers}
    req = Request(scope)

    principal = await provider.authenticate(req)
    # Principal MUST be User A (derived strictly from cryptographic token), NEVER User B
    assert principal.user_id == user_a
    assert principal.user_id != user_b


@pytest.mark.asyncio
async def test_development_auth_provider_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = DevelopmentAuthProvider()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)

    scope = {"type": "http", "headers": []}
    req = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        await provider.authenticate(req)
    assert exc_info.value.status_code == 500
    assert "cannot be used in production" in exc_info.value.detail


def test_get_auth_provider_returns_production_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    provider = get_auth_provider()
    assert isinstance(provider, ProductionAuthProvider)


@pytest.mark.asyncio
async def test_production_auth_rejects_unauthenticated_without_dev_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    provider = get_auth_provider()

    req = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        await provider.authenticate(req)
    assert exc_info.value.status_code == 401
    assert "Authorization header missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_production_auth_rejects_x_user_id_without_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    provider = get_auth_provider()

    spoofed_user = uuid.uuid4()
    headers = [(b"x-user-id", str(spoofed_user).encode("utf-8"))]
    req = Request({"type": "http", "headers": headers})

    with pytest.raises(HTTPException) as exc_info:
        await provider.authenticate(req)
    assert exc_info.value.status_code == 401
    assert "Authorization header missing" in exc_info.value.detail

