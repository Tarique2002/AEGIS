"""Unit tests for 7-Stage SafetyGate pipeline."""

import uuid

import pytest
from app.safety.gates import SafetyGate
from app.safety.schemas import SafetyContext, SafetyDecisionType


@pytest.mark.asyncio
async def test_safety_gate_allow_low_risk() -> None:
    gate = SafetyGate()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="calculate math",
        tool_name="calculator",
        arguments_metadata={"expression": "10 * 10"},
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is True
    assert decision.decision_type == SafetyDecisionType.ALLOW
    assert len(decision.gate_results) == 7


@pytest.mark.asyncio
async def test_safety_gate_deny_unauthenticated() -> None:
    gate = SafetyGate()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="calculate",
        authenticated=False,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.decision_type == SafetyDecisionType.DENY
    assert "Unauthenticated" in decision.reason


@pytest.mark.asyncio
async def test_safety_gate_deny_destructive() -> None:
    gate = SafetyGate()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="destroy all data",
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.decision_type == SafetyDecisionType.DENY
