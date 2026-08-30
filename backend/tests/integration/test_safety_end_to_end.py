"""End-to-End integration tests for Safety verification."""

import uuid

import pytest
from app.safety.gates import SafetyGate
from app.safety.schemas import SafetyContext, SafetyDecisionType


@pytest.mark.asyncio
async def test_end_to_end_benign_calculator_flow() -> None:
    gate = SafetyGate()
    user_id = uuid.uuid4()
    ctx = SafetyContext(
        user_id=user_id,
        action="calculate",
        tool_name="calculator",
        arguments_metadata={"expression": "42 * 2"},
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is True
    assert decision.decision_type == SafetyDecisionType.ALLOW


@pytest.mark.asyncio
async def test_end_to_end_high_risk_requires_approval() -> None:
    gate = SafetyGate()
    user_id = uuid.uuid4()
    ctx = SafetyContext(
        user_id=user_id,
        action="external_network_call",
        arguments_metadata={"url": "https://api.external-partner.com/query"},
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.decision_type == SafetyDecisionType.REQUIRE_APPROVAL
    assert decision.required_approval is True


@pytest.mark.asyncio
async def test_end_to_end_code_execution_denied() -> None:
    gate = SafetyGate()
    user_id = uuid.uuid4()
    ctx = SafetyContext(
        user_id=user_id,
        action="run_python_eval_exec",
        arguments_metadata={"code": "import os; os.system('ls')"},
        authenticated=True,
    )
    decision = await gate.evaluate(ctx)
    assert decision.allowed is False
    assert decision.decision_type == SafetyDecisionType.DENY
