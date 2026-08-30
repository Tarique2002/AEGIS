"""Unit tests for Budget Gate and resource tracking."""

import uuid

import pytest
from app.safety.gates import SafetyGate
from app.safety.schemas import SafetyContext


@pytest.mark.asyncio
async def test_budget_gate_pass() -> None:
    gate = SafetyGate()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="execute_step",
        budget_remaining={"iterations": 10, "tool_calls": 5},
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is True
