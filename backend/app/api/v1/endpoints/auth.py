"""FastAPI router endpoints for Authentication, Identity, and Token Revocation."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_principal
from app.core.auth import AuthenticatedPrincipal, create_access_token, revoke_token
from app.core.logging import get_logger
from app.schemas.common import AegisBaseSchema

logger = get_logger("aegis.api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


class TokenIssueRequest(AegisBaseSchema):
    """Payload to request an operator or demo access token."""

    user_id: uuid.UUID | None = None
    email: str | None = "operator@aegis.io"
    roles: list[str] = ["ADMIN", "OPERATOR"]
    scopes: list[str] = ["*"]
    expires_in_seconds: int = 86400


class TokenIssueResponse(AegisBaseSchema):
    """Generated JWT access token and session metadata."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: uuid.UUID
    email: str | None
    roles: list[str]
    scopes: list[str]


@router.post(
    "/token",
    response_model=TokenIssueResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue a signed JWT access token for operator or demo session",
)
async def issue_access_token(
    request: TokenIssueRequest | None = None,
) -> TokenIssueResponse:
    """
    Issue a cryptographically signed HMAC-SHA256 Bearer access token using the active server key.
    Provides immediate authentication credentials for control plane operators and automated callers.
    """
    req = request or TokenIssueRequest()
    uid = req.user_id or uuid.uuid4()
    expires = req.expires_in_seconds if req.expires_in_seconds > 0 else 86400
    token = create_access_token(
        user_id=uid,
        email=req.email,
        roles=req.roles,
        scopes=req.scopes,
        expires_in_seconds=expires,
    )
    logger.info(f"Issued access token for user {uid} ({req.email}) with roles {req.roles}")
    return TokenIssueResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires,
        user_id=uid,
        email=req.email,
        roles=req.roles,
        scopes=req.scopes,
    )


class TokenRevokeRequest(AegisBaseSchema):
    """Payload to revoke current or specific session token."""

    token_id: str | None = None


class TokenRevokeResponse(AegisBaseSchema):
    """Status confirmation of token revocation."""

    message: str
    revoked_token_id: str
    user_id: uuid.UUID


@router.post(
    "/revoke",
    response_model=TokenRevokeResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke caller's current session or access token",
)
async def revoke_current_token(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    request: TokenRevokeRequest | None = None,
) -> TokenRevokeResponse:
    """
    Revoke caller's active bearer token session.
    A user may only revoke their own authenticated token identifier.
    """
    target_token_id = (
        request.token_id if request and request.token_id else principal.token_id
    ) or str(uuid.uuid4())

    await revoke_token(target_token_id)
    logger.info(f"User {principal.user_id} revoked token identifier '{target_token_id}'")

    return TokenRevokeResponse(
        message="Token successfully revoked.",
        revoked_token_id=target_token_id,
        user_id=principal.user_id,
    )
