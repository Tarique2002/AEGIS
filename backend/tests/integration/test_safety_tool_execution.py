"""Integration tests for Safety Gate protection in Tool Execution."""

import uuid

import pytest
from app.safety.gates import SafetyGate
from app.safety.policies import SafetyPolicy
from app.safety.schemas import RiskLevel
from app.tools.executor import ToolExecutor
from app.tools.schemas import InvocationStatus, ToolInvocation


@pytest.mark.asyncio
async def test_tool_execution_safe_calculator() -> None:
    safety_gate = SafetyGate()
    executor = ToolExecutor(safety_gate=safety_gate)

    invocation = ToolInvocation(
        invocation_id=uuid.uuid4(),
        tool_name="calculator",
        arguments={"expression": "100 / 4"},
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
    )
    obs = await executor.execute(invocation)
    assert obs.success is True
    assert obs.status == InvocationStatus.COMPLETED
    assert obs.output == {"expression": "100 / 4", "result": 25}


@pytest.mark.asyncio
async def test_tool_execution_blocked_by_safety_gate() -> None:
    # Restrict max risk to NONE
    strict_policy = SafetyPolicy(max_risk_level=RiskLevel.NONE)
    safety_gate = SafetyGate(policy=strict_policy)
    executor = ToolExecutor(safety_gate=safety_gate)

    invocation = ToolInvocation(
        invocation_id=uuid.uuid4(),
        tool_name="calculator",
        arguments={"expression": "50 + 50"},
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
    )
    obs = await executor.execute(invocation)
    assert obs.success is False
    assert obs.status == InvocationStatus.REJECTED
    assert "Safety Gate Denied" in (obs.error or "")
