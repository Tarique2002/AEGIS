"""Unit tests for DecisionEngine and deterministic rule evaluation."""

import uuid

import pytest
from app.agent_loop.budget import AgentBudget
from app.agent_loop.decision import DecisionEngine
from app.agent_loop.guardrails import ProgressTracker
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentObservation, DecisionType
from app.evaluation.schemas import CriterionScore, EvaluationResult
from app.planner.schemas import PlanExecutionResponse, PlanStatus


@pytest.mark.asyncio
async def test_decision_engine_evaluation_passed_completes() -> None:
    policy = AgentLoopPolicy(completion_score_threshold=0.8)
    engine = DecisionEngine(policy=policy)
    budget = AgentBudget(policy=policy)
    tracker = ProgressTracker(policy=policy)

    eval_res = EvaluationResult(
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        passed=True,
        overall_score=0.92,
        scores=[
            CriterionScore(
                criterion_id="correctness",
                criterion_name="Correctness",
                score=0.92,
                weight=1.0,
                justification="Accurate execution.",
            )
        ],
        summary="Accurate and complete execution.",
    )

    obs = AgentObservation(
        iteration_number=1,
        evaluation_result=eval_res,
    )

    decision = await engine.make_decision(obs, tracker, budget, objective="Calculate 50 + 50")
    assert decision.decision_type == DecisionType.COMPLETE
    assert "Objective satisfied" in decision.rationale


@pytest.mark.asyncio
async def test_decision_engine_failure_triggers_replan() -> None:
    policy = AgentLoopPolicy()
    engine = DecisionEngine(policy=policy)
    budget = AgentBudget(policy=policy)
    tracker = ProgressTracker(policy=policy)

    exec_res = PlanExecutionResponse(
        plan_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        status=PlanStatus.FAILED,
        completed_nodes=[],
        failed_nodes=["calc_node"],
        errors={"calc_node": "Division by zero"},
    )

    obs = AgentObservation(
        iteration_number=1,
        execution_results=exec_res,
        active_errors=["Division by zero"],
    )

    decision = await engine.make_decision(obs, tracker, budget, objective="Divide by zero safe")
    assert decision.decision_type == DecisionType.REPLAN
    assert decision.next_plan_required is True


@pytest.mark.asyncio
async def test_decision_engine_stagnation_triggers_fail() -> None:
    policy = AgentLoopPolicy(max_stagnant_iterations=2)
    engine = DecisionEngine(policy=policy)
    budget = AgentBudget(policy=policy)
    tracker = ProgressTracker(policy=policy)

    # Initial score + 2 stagnant iterations
    tracker.record_iteration(eval_score=0.4)
    tracker.record_iteration(eval_score=0.4)
    tracker.record_iteration(eval_score=0.4)

    obs = AgentObservation(iteration_number=3)
    decision = await engine.make_decision(obs, tracker, budget, objective="Stuck loop")
    assert decision.decision_type == DecisionType.FAIL
    assert "Stagnation detected" in decision.rationale
