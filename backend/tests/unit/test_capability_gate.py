"""Unit tests for Budget Gate and Capability Gate."""

import uuid

import pytest
from app.safety.gates import SafetyGate
from app.safety.schemas import SafetyContext, SafetyDecisionType


@pytest.mark.asyncio
async def test_capability_gate_forbidden_capabilities() -> None:
    gate = SafetyGate()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="dispatch_worker",
        requested_capabilities=["shell", "os_system"],
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.decision_type == SafetyDecisionType.DENY
    assert "Forbidden capability" in decision.reason


@pytest.mark.asyncio
async def test_capability_gate_allowed_capabilities() -> None:
    gate = SafetyGate()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="dispatch_worker",
        requested_capabilities=["logic", "algorithmic_reasoning"],
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is True
