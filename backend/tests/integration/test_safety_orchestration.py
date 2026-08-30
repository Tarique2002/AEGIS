"""Integration tests for Safety Gate integration in Multi-Agent Orchestration."""

import uuid
from unittest.mock import AsyncMock

import pytest
from app.orchestration.orchestrator import MultiAgentOrchestrator
from app.orchestration.schemas import OrchestrationStatus
from app.safety.gates import SafetyGate
from app.safety.policies import SafetyPolicy
from app.safety.schemas import RiskLevel
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_orchestration_blocked_by_safety_gate(db_session: AsyncSession) -> None:
    # Strict policy rejecting all risk
    strict_policy = SafetyPolicy(max_risk_level=RiskLevel.NONE)
    safety_gate = SafetyGate(policy=strict_policy)

    mock_agent_loop_service = AsyncMock()
    orchestrator = MultiAgentOrchestrator(
        agent_loop_service=mock_agent_loop_service,
        safety_gate=safety_gate,
    )

    state = await orchestrator.execute_orchestration(
        orchestration_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        objective="Analyze complex data and synthesize answer",
        session=db_session,
    )

    assert state.status == OrchestrationStatus.FAILED
    assert any("Safety Gate Denied" in err for err in state.errors)
