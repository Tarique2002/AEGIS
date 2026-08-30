"""Unit tests for AgentRuntime execution, state persistence, telemetry, and event trace."""

import uuid

import pytest
from app.agents.runtime import AgentRuntime
from app.core.errors import LLMProviderError
from app.db.models.event import ExecutionEventModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.llm.providers.mock import MockLLMProvider
from app.observability.events import EventEmitter
from app.schemas.common import TaskStatus
from app.schemas.event import ExecutionEventType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_agent_runtime_successful_execution(db_session: AsyncSession):
    mock_provider = MockLLMProvider(
        model_name="mock-llama-3",
        default_response_text="PostgreSQL indexes use B-Trees to speed up queries.",
        prompt_tokens=120,
        completion_tokens=45,
    )
    emitter = EventEmitter()
    runtime = AgentRuntime(provider=mock_provider, emitter=emitter)

    task_id = uuid.uuid4()
    objective = "Explain how PostgreSQL indexing works."

    state = await runtime.execute_task(
        objective=objective,
        session=db_session,
        task_id=task_id,
    )

    # 1. State verification
    assert state.task_id == task_id
    assert state.run_id is not None
    assert state.status == TaskStatus.COMPLETED
    assert state.final_result == "PostgreSQL indexes use B-Trees to speed up queries."
    assert len(state.messages) == 3  # System, User, Assistant
    assert state.started_at is not None
    assert state.completed_at is not None
    assert state.telemetry is not None
    assert state.telemetry.total_tokens == 165
    assert state.telemetry.prompt_tokens == 120
    assert state.telemetry.completion_tokens == 45
    assert state.telemetry.estimated_cost_usd is None

    # 2. Database persistence verification
    task_stmt = select(Task).where(Task.id == task_id)
    task_res = await db_session.execute(task_stmt)
    task_db = task_res.scalar_one()

    assert task_db.status == "completed"
    assert task_db.result == "PostgreSQL indexes use B-Trees to speed up queries."
    assert task_db.completed_at is not None

    run_stmt = select(AgentRun).where(AgentRun.task_id == task_id)
    run_res = await db_session.execute(run_stmt)
    run_db = run_res.scalar_one()

    assert run_db.id == state.run_id
    assert run_db.status == "completed"
    assert run_db.result == "PostgreSQL indexes use B-Trees to speed up queries."
    assert run_db.total_tokens == 165
    assert run_db.state_snapshot is not None
    assert run_db.state_snapshot["status"] == "completed"

    # 3. Execution events & monotonic sequence verification
    events_stmt = (
        select(ExecutionEventModel)
        .where(ExecutionEventModel.run_id == state.run_id)
        .order_by(ExecutionEventModel.sequence_number.asc())
    )
    events_res = await db_session.execute(events_stmt)
    events_db = events_res.scalars().all()

    assert len(events_db) >= 6
    sequence_numbers = [e.sequence_number for e in events_db]
    assert sequence_numbers == list(range(1, len(events_db) + 1))  # [1, 2, 3, 4, 5, 6, 7]

    event_types = [e.event_type for e in events_db]
    assert ExecutionEventType.RUN_STARTED.value in event_types
    assert ExecutionEventType.MODEL_CALL_STARTED.value in event_types
    assert ExecutionEventType.MODEL_CALL_COMPLETED.value in event_types
    assert ExecutionEventType.STATE_TRANSITION.value in event_types
    assert ExecutionEventType.RUN_COMPLETED.value in event_types
    assert ExecutionEventType.TASK_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_agent_runtime_failure_handling(db_session: AsyncSession):
    failing_provider = MockLLMProvider(
        should_fail=True,
        failure_message="Simulated LLM API rate limit / 503",
    )
    emitter = EventEmitter()
    runtime = AgentRuntime(provider=failing_provider, emitter=emitter)

    task_id = uuid.uuid4()
    objective = "Task destined to fail"

    with pytest.raises(LLMProviderError) as exc_info:
        await runtime.execute_task(
            objective=objective,
            session=db_session,
            task_id=task_id,
        )

    assert "Simulated LLM API rate limit" in str(exc_info.value)

    # Verify task and run were marked as FAILED in PostgreSQL
    task_stmt = select(Task).where(Task.id == task_id)
    task_res = await db_session.execute(task_stmt)
    task_db = task_res.scalar_one()
    assert task_db.status == "failed"

    run_stmt = select(AgentRun).where(AgentRun.task_id == task_id)
    run_res = await db_session.execute(run_stmt)
    run_db = run_res.scalar_one()
    assert run_db.status == "failed"
    assert "Simulated LLM API rate limit" in (run_db.error or "")

    # Verify failure events were emitted
    events_stmt = (
        select(ExecutionEventModel)
        .where(ExecutionEventModel.run_id == run_db.id)
        .order_by(ExecutionEventModel.sequence_number.asc())
    )
    events_res = await db_session.execute(events_stmt)
    events_db = events_res.scalars().all()
    event_types = [e.event_type for e in events_db]

    assert ExecutionEventType.RUN_FAILED.value in event_types
    assert ExecutionEventType.TASK_FAILED.value in event_types
