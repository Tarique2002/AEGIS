"""Authentication, Identity Trust Boundaries, and Principal context for AEGIS."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Protocol

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import Environment, Settings
from app.core.logging import get_logger

logger = get_logger("aegis.core.auth")

DEFAULT_DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class AuthenticatedPrincipal(BaseModel):
    """
    Immutable identity context representing an authenticated actor.
    Derived strictly from verified credentials/session, never from unverified request bodies.
    """

    user_id: uuid.UUID
    email: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["user"])
    scopes: list[str] = Field(default_factory=list)
    is_authenticated: bool = True
    auth_scheme: str = "bearer"
    token_id: str | None = None


# In-memory revocation cache fallback (for tests and dev)
_revoked_tokens_cache: set[str] = set()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def is_token_revoked(token_id_or_hash: str) -> bool:
    """Check if token identifier has been revoked."""
    if token_id_or_hash in _revoked_tokens_cache:
        return True
    return False


async def is_token_revoked_async(token_id_or_hash: str) -> bool:
    """Check if token identifier has been revoked in Redis or in-memory cache."""
    if token_id_or_hash in _revoked_tokens_cache:
        return True
    try:
        from app.db.redis import get_redis_client

        client = get_redis_client()
        res = await client.get(f"aegis:auth:revoked:{token_id_or_hash}")
        if res is not None:
            _revoked_tokens_cache.add(token_id_or_hash)
            return True
    except Exception:
        pass
    return False


async def revoke_token(token_id_or_hash: str, ttl_seconds: int = 3600) -> None:
    """Revoke a token identifier by writing to Redis and in-memory blacklist."""
    _revoked_tokens_cache.add(token_id_or_hash)
    try:
        from app.db.redis import get_redis_client

        client = get_redis_client()
        await client.setex(f"aegis:auth:revoked:{token_id_or_hash}", ttl_seconds, "revoked")
    except Exception as exc:
        logger.warning(f"Could not persist token revocation to Redis: {exc}")


def create_access_token(
    user_id: uuid.UUID,
    email: str | None = None,
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
    expires_in_seconds: int = 3600,
    secret_key: str | None = None,
    token_id: str | None = None,
) -> str:
    """
    Generate a cryptographically signed HMAC-SHA256 Bearer access token with jti and scopes.
    """
    settings = Settings()
    key = (secret_key or settings.effective_jwt_secret).encode("utf-8")
    jti = token_id or str(uuid.uuid4())

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "email": email,
        "roles": roles or ["user"],
        "scopes": scopes or [],
        "jti": jti,
        "exp": int(time.time()) + expires_in_seconds,
        "iat": int(time.time()),
    }

    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode()

    signature = hmac.new(key, signing_input, hashlib.sha256).digest()
    signature_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_access_token(
    token: str,
    secret_key: str | None = None,
) -> AuthenticatedPrincipal:
    """
    Verify signature, expiration, and payload of a signed access token.
    """
    settings = Settings()
    key = (secret_key or settings.effective_jwt_secret).encode("utf-8")

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token structure.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(key, signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _b64decode(signature_b64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token signature encoding.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(sub)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject UUID format.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    jti = payload.get("jti") or hashlib.sha256(token.encode()).hexdigest()
    if is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedPrincipal(
        user_id=user_uuid,
        email=payload.get("email"),
        roles=payload.get("roles", ["user"]),
        scopes=payload.get("scopes", []),
        is_authenticated=True,
        auth_scheme="bearer",
        token_id=jti,
    )


class AuthProvider(Protocol):
    """Interface for authenticating incoming HTTP requests."""

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        """Extract and authenticate principal from request."""
        ...


class ProductionAuthProvider:
    """
    Production authentication provider.
    Enforces cryptographically signed Bearer tokens and strictly ignores client-supplied
    custom identity headers.
    """

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Authorization header missing.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization format. Expected 'Bearer <token>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # In production, custom headers like X-User-Id are strictly ignored for trust
        principal = verify_access_token(parts[1])
        return principal


class DevelopmentAuthProvider:
    """
    Explicit development authentication adapter for local dev and automated test suites.
    Only permitted when ENVIRONMENT is 'development' or 'testing'.
    """

    def __init__(self, default_user_id: uuid.UUID = DEFAULT_DEV_USER_ID) -> None:
        self.default_user_id = default_user_id

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        settings = Settings()
        if settings.ENVIRONMENT in (Environment.PRODUCTION, Environment.STAGING):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DevelopmentAuthProvider cannot be used in production environments.",
            )

        # 1. Check Bearer token first if provided
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return verify_access_token(parts[1])

        # 2. Check explicit dev header if provided
        dev_user_header = request.headers.get("X-User-Id")
        if dev_user_header:
            try:
                user_uuid = uuid.UUID(dev_user_header)
                return AuthenticatedPrincipal(
                    user_id=user_uuid,
                    auth_scheme="dev_adapter",
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid X-User-Id header format. Must be a valid UUID.",
                ) from exc

        # 3. Fall back to default development principal
        return AuthenticatedPrincipal(
            user_id=self.default_user_id,
            auth_scheme="dev_default",
        )


def get_auth_provider() -> AuthProvider:
    """Factory providing appropriate authentication provider based on environment."""
    settings = Settings()
    if settings.ENVIRONMENT in (Environment.PRODUCTION, Environment.STAGING):
        return ProductionAuthProvider()
    return DevelopmentAuthProvider()


async def get_current_principal(
    request: Request,
) -> AuthenticatedPrincipal:
    """
    Extract and verify trusted authenticated principal for current request.
    """
    provider = get_auth_provider()
    return await provider.authenticate(request)


async def get_current_user_id(
    request: Request,
) -> uuid.UUID:
    """
    Extract trusted user UUID from authenticated principal.
    """
    principal = await get_current_principal(request)
    return principal.user_id
