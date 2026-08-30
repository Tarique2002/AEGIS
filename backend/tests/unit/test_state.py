"""Unit tests for Agent State models and timezone handling."""

import uuid
from datetime import UTC

import pytest
from app.schemas.common import RiskLevel, StepStatus, TaskStatus, utc_now
from app.schemas.state import (
    AgentState,
    Plan,
    PlanStep,
    RetrievedMemoryItem,
    TokenUsage,
    ToolInvocation,
    ToolObservation,
)
from pydantic import ValidationError


def test_timezone_aware_utc_now():
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC


def test_agent_state_creation_and_defaults():
    task_id = uuid.uuid4()
    state = AgentState(
        task_id=task_id,
        objective="Analyze market trends and summarize findings",
    )

    assert state.task_id == task_id
    assert state.objective == "Analyze market trends and summarize findings"
    assert state.status == TaskStatus.PENDING
    assert state.created_at.tzinfo == UTC
    assert state.updated_at.tzinfo == UTC
    assert state.tool_calls == []
    assert state.observations == []
    assert state.retrieved_memories == []
    assert state.retries_count == 0
    assert state.max_retries == 3
    assert state.usage.total_tokens == 0


def test_agent_state_with_full_plan_and_tool_execution():
    task_id = uuid.uuid4()
    step_1 = PlanStep(
        order=1,
        title="Search web",
        description="Search for quarterly reports",
        required_tools=["web_search"],
        status=StepStatus.COMPLETED,
        result="Found 5 reports",
    )
    plan = Plan(
        objective="Analyze quarterly reports",
        steps=[step_1],
    )

    tool_call = ToolInvocation(
        step_id=step_1.step_id,
        tool_name="web_search",
        arguments={"query": "Q3 2026 reports"},
        risk_level=RiskLevel.LOW,
    )

    observation = ToolObservation(
        call_id=tool_call.call_id,
        tool_name="web_search",
        success=True,
        output={"results": ["Report 1", "Report 2"]},
        latency_ms=245.5,
    )

    memory_item = RetrievedMemoryItem(
        memory_id="mem-123",
        memory_type="procedural",
        content="Always verify report authenticity",
        relevance_score=0.92,
    )

    state = AgentState(
        task_id=task_id,
        objective="Analyze quarterly reports",
        status=TaskStatus.EXECUTING,
        current_plan=plan,
        current_step_id=step_1.step_id,
        completed_steps=[step_1.step_id],
        tool_calls=[tool_call],
        observations=[observation],
        retrieved_memories=[memory_item],
        usage=TokenUsage(
            prompt_tokens=500,
            completion_tokens=150,
            total_tokens=650,
            estimated_cost_usd=0.005,
        ),
    )

    # Validate JSON serialization & deserialization cycle
    json_str = state.model_dump_json()
    assert "web_search" in json_str
    assert "mem-123" in json_str

    reconstructed = AgentState.model_validate_json(json_str)
    assert reconstructed.task_id == task_id
    assert reconstructed.current_plan is not None
    assert len(reconstructed.current_plan.steps) == 1
    assert reconstructed.current_plan.steps[0].title == "Search web"
    assert reconstructed.observations[0].success is True
    assert reconstructed.observations[0].timestamp.tzinfo is not None
    assert reconstructed.usage.total_tokens == 650


def test_agent_state_validation_error():
    with pytest.raises(ValidationError):
        # Missing required task_id and objective
        AgentState()  # type: ignore


def test_agent_state_valid_lifecycle_transitions():
    task_id = uuid.uuid4()
    state = AgentState(
        task_id=task_id,
        objective="Explain database indexing",
        status=TaskStatus.PENDING,
    )
    assert state.status == TaskStatus.PENDING
    assert state.started_at is None
    assert state.completed_at is None

    # Valid transition: PENDING -> RUNNING
    state.transition_to(TaskStatus.RUNNING)
    assert state.status == TaskStatus.RUNNING
    assert state.started_at is not None
    assert state.completed_at is None

    # Valid transition: RUNNING -> COMPLETED
    state.transition_to(TaskStatus.COMPLETED)
    assert state.status == TaskStatus.COMPLETED
    assert state.completed_at is not None


def test_agent_state_failure_transition():
    task_id = uuid.uuid4()
    state = AgentState(
        task_id=task_id,
        objective="Test failure transition",
        status=TaskStatus.PENDING,
    )
    state.transition_to(TaskStatus.RUNNING)
    state.transition_to(TaskStatus.FAILED)
    assert state.status == TaskStatus.FAILED
    assert state.completed_at is not None


def test_agent_state_cancellation_transition():
    task_id = uuid.uuid4()
    state = AgentState(
        task_id=task_id,
        objective="Test cancellation transition",
        status=TaskStatus.PENDING,
    )
    state.transition_to(TaskStatus.CANCELLED)
    assert state.status == TaskStatus.CANCELLED
    assert state.completed_at is not None


def test_agent_state_invalid_transitions():
    from app.core.errors import InvalidStateTransitionError

    task_id = uuid.uuid4()
    state = AgentState(
        task_id=task_id,
        objective="Test invalid transitions",
        status=TaskStatus.PENDING,
    )

    # Invalid: PENDING -> COMPLETED directly without running
    with pytest.raises(InvalidStateTransitionError):
        state.transition_to(TaskStatus.COMPLETED)

    # Advance to COMPLETED (terminal)
    state.transition_to(TaskStatus.RUNNING)
    state.transition_to(TaskStatus.COMPLETED)

    # Invalid: COMPLETED -> RUNNING (out of terminal)
    with pytest.raises(InvalidStateTransitionError):
        state.transition_to(TaskStatus.RUNNING)

    # Invalid: COMPLETED -> FAILED (out of terminal)
    with pytest.raises(InvalidStateTransitionError):
        state.transition_to(TaskStatus.FAILED)
