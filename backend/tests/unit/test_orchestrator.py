"""Unit tests for MultiAgentOrchestrator lifecycle and bounded rework."""

import uuid
from unittest.mock import AsyncMock

import pytest
from app.agent_loop.schemas import AgentBudgetState, AgentLoopResponse, AgentLoopStatus
from app.agent_loop.service import AgentLoopService
from app.evaluation.schemas import EvaluationResult
from app.evaluation.service import EvaluationService
from app.orchestration.orchestrator import MultiAgentOrchestrator
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import OrchestrationStatus
from app.schemas.common import utc_now


@pytest.mark.asyncio
async def test_orchestrator_lifecycle_success() -> None:
    loop_service = AsyncMock(spec=AgentLoopService)

    # Mock agent loop execution returning success
    loop_service.create_and_start_loop.return_value = AgentLoopResponse(
        loop_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        objective="Calculate",
        iteration_number=1,
        status=AgentLoopStatus.COMPLETED,
        final_result={"result": 60},
        budget=AgentBudgetState(total_iterations=1, total_tool_calls=1, total_llm_calls=1),
        started_at=utc_now(),
        updated_at=utc_now(),
    )

    eval_service = AsyncMock(spec=EvaluationService)
    eval_service.evaluate_run.return_value = EvaluationResult(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        passed=True,
        overall_score=0.95,
        criteria_scores=[],
        strengths=["Clear calculation"],
        weaknesses=[],
    )

    orchestrator = MultiAgentOrchestrator(
        agent_loop_service=loop_service,
        evaluation_service=eval_service,
    )

    state = await orchestrator.execute_orchestration(
        orchestration_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        objective="Calculate 10 + 20 + 30",
        session=AsyncMock(),
    )

    assert state.status == OrchestrationStatus.COMPLETED
    assert state.aggregated_result is not None
    assert state.budget.completed_workers == 3
    assert state.budget.rework_rounds == 0


@pytest.mark.asyncio
async def test_orchestrator_bounded_rework_trigger() -> None:
    loop_service = AsyncMock(spec=AgentLoopService)

    loop_service.create_and_start_loop.return_value = AgentLoopResponse(
        loop_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        objective="Calculate",
        iteration_number=1,
        status=AgentLoopStatus.COMPLETED,
        final_result={"result": "incomplete"},
        budget=AgentBudgetState(),
        started_at=utc_now(),
        updated_at=utc_now(),
    )

    # Low evaluation score triggers bounded rework
    eval_service = AsyncMock(spec=EvaluationService)
    eval_service.evaluate_run.return_value = EvaluationResult(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        passed=False,
        overall_score=0.5,  # below 0.85 threshold
        criteria_scores=[],
        strengths=[],
        weaknesses=["Incomplete reasoning"],
    )

    policy = OrchestrationPolicy(max_rework_rounds=1, completion_score_threshold=0.85)
    orchestrator = MultiAgentOrchestrator(
        agent_loop_service=loop_service,
        evaluation_service=eval_service,
        policy=policy,
    )

    state = await orchestrator.execute_orchestration(
        orchestration_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        objective="Calculate complex problem",
        session=AsyncMock(),
    )

    assert state.budget.rework_rounds == 1
    assert "Rework round 1 applied" in str(state.aggregated_result.summary)
