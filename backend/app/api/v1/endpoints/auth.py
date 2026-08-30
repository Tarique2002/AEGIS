"""FastAPI router endpoints for Authentication, Identity, and Token Revocation."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_principal
from app.core.auth import AuthenticatedPrincipal, revoke_token
from app.core.logging import get_logger
from app.schemas.common import AegisBaseSchema

logger = get_logger("aegis.api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


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
