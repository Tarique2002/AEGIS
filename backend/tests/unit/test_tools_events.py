"""Unit tests for tool execution events and monotonic sequence ordering."""

import uuid

import pytest
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType
from app.tools.executor import ToolExecutor
from app.tools.schemas import ToolInvocation


@pytest.mark.asyncio
async def test_tool_events_monotonic_sequence():
    emitter = EventEmitter()
    executor = ToolExecutor(emitter=emitter)

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    # Pre-emit initial model lifecycle events to simulate a real multi-step run
    await emitter.emit(task_id, run_id, ExecutionEventType.RUN_STARTED, {"step": 1})
    await emitter.emit(task_id, run_id, ExecutionEventType.MODEL_CALL_STARTED, {})
    await emitter.emit(task_id, run_id, ExecutionEventType.MODEL_CALL_COMPLETED, {})

    # Execute tool
    inv = ToolInvocation(
        tool_name="calculator",
        arguments={"expression": "50 * 2"},
        task_id=task_id,
        run_id=run_id,
    )
    await executor.execute(inv)

    # Post-emit run completion
    await emitter.emit(task_id, run_id, ExecutionEventType.RUN_COMPLETED, {})

    events = emitter.get_events_for_run(run_id)
    assert len(events) == 7

    # Verify strict monotonic sequence numbering (1 to 7)
    seqs = [e.sequence_number for e in events]
    assert seqs == [1, 2, 3, 4, 5, 6, 7]

    types = [e.event_type for e in events]
    assert types == [
        ExecutionEventType.RUN_STARTED,
        ExecutionEventType.MODEL_CALL_STARTED,
        ExecutionEventType.MODEL_CALL_COMPLETED,
        ExecutionEventType.TOOL_CALL_REQUESTED,
        ExecutionEventType.TOOL_CALL_STARTED,
        ExecutionEventType.TOOL_CALL_COMPLETED,
        ExecutionEventType.RUN_COMPLETED,
    ]
