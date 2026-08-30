import uuid

import pytest
from app.safety.gates import SafetyGate
from app.safety.schemas import SafetyContext
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_authorization_gate_valid_user() -> None:
    gate = SafetyGate()
    user_id = uuid.uuid4()
    ctx = SafetyContext(
        user_id=user_id,
        action="read_state",
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_authorization_gate_invalid_user_type() -> None:
    with pytest.raises(ValidationError):
        SafetyContext(
            user_id="invalid-not-a-uuid",  # type: ignore
            action="read_state",
            authenticated=True,
        )
