"""Unit tests for token session revocation."""

import uuid

import pytest
from app.core.auth import (
    create_access_token,
    is_token_revoked,
    revoke_token,
    verify_access_token,
)
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_token_creation_and_revocation() -> None:
    user_id = uuid.uuid4()
    token_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, token_id=token_id)

    principal = verify_access_token(token)
    assert principal.user_id == user_id
    assert principal.token_id == token_id

    # Revoke token
    await revoke_token(token_id)
    assert is_token_revoked(token_id) is True

    # Verification must now fail with 401
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail
