"""Unified FastAPI dependency providers for authentication and trusted context."""

import uuid
from typing import Annotated

from fastapi import Depends, Request

from app.core.auth import (
    AuthenticatedPrincipal,
    AuthProvider,
    get_auth_provider,
)


async def get_current_principal(
    request: Request,
    auth_provider: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> AuthenticatedPrincipal:
    """
    Extract and verify trusted authenticated principal for the current request.
    Enforces security boundary preventing untrusted request body/headers from dictating identity.
    """
    return await auth_provider.authenticate(request)


# Alias for backward/explicit endpoint consistency
get_current_user_principal = get_current_principal


async def get_current_user_id(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> uuid.UUID:
    """
    Extract trusted user UUID from authenticated principal.
    """
    return principal.user_id


def require_scope(required_scope: str):
    """Dependency factory enforcing that the token contains the specified scope."""

    async def _scope_checker(
        principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    ) -> AuthenticatedPrincipal:
        from app.authz.service import AuthorizationService

        authz = AuthorizationService()
        authz.require_scope(principal, required_scope)
        return principal

    return _scope_checker


get_required_scope = require_scope
