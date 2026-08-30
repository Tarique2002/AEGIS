"""Unit tests for agent loop schemas, state models, and status lifecycle."""

import uuid

from app.agent_loop.schemas import (
    AgentDecision,
    AgentIterationRecord,
    AgentLoopState,
    AgentLoopStatus,
    AgentObservation,
    AutonomyLevel,
    DecisionType,
)


def test_agent_loop_state_defaults() -> None:
    loop_id = uuid.uuid4()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()

    state = AgentLoopState(
        loop_id=loop_id,
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        objective="Execute multi-step calculation",
    )

    assert state.loop_id == loop_id
    assert state.iteration_number == 0
    assert state.status == AgentLoopStatus.CREATED
    assert state.budget.iterations == 0
    assert state.completed_iterations == []
    assert state.final_result is None


def test_agent_observation_schema() -> None:
    obs = AgentObservation(
        iteration_number=1,
        task_state={"step": "init"},
        active_errors=["timeout"],
        available_actions=["replan", "complete"],
    )
    assert obs.iteration_number == 1
    assert obs.active_errors == ["timeout"]
    assert "replan" in obs.available_actions


def test_agent_decision_schema() -> None:
    decision = AgentDecision(
        iteration_number=2,
        decision_type=DecisionType.REPLAN,
        rationale="Previous step failed; revised arithmetic strategy needed.",
        confidence=0.95,
        next_plan_required=True,
    )
    assert decision.decision_type == DecisionType.REPLAN
    assert decision.confidence == 0.95
    assert decision.next_plan_required is True


def test_agent_iteration_record_validation() -> None:
    rec = AgentIterationRecord(
        loop_id=uuid.uuid4(),
        iteration_number=1,
        status=AgentLoopStatus.COMPLETED,
    )
    assert rec.status == AgentLoopStatus.COMPLETED
    assert rec.error is None


def test_autonomy_level_enum() -> None:
    assert AutonomyLevel.BOUNDED.value == "BOUNDED"
    assert AutonomyLevel.SUPERVISED.value == "SUPERVISED"
    assert AutonomyLevel.AUTONOMOUS.value == "AUTONOMOUS"
