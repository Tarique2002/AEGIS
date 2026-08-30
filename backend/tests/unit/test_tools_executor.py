"""Unit tests for ToolExecutor execution boundary, timeout, exception isolation, and telemetry."""

import asyncio
import uuid

import pytest
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType
from app.tools.base import BaseTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, create_default_tool_registry
from app.tools.schemas import (
    InvocationStatus,
    ToolDefinition,
    ToolInvocation,
    ToolPolicyClassification,
)


@pytest.mark.asyncio
async def test_executor_successful_execution():
    registry = create_default_tool_registry()
    emitter = EventEmitter()
    executor = ToolExecutor(registry=registry, emitter=emitter)

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    invocation = ToolInvocation(
        tool_name="calculator",
        arguments={"expression": "(25 * 4) + 10"},
        task_id=task_id,
        run_id=run_id,
    )

    observation = await executor.execute(invocation)

    assert observation.success is True
    assert observation.status == InvocationStatus.COMPLETED
    assert observation.output["result"] == 110
    assert observation.error is None
    assert observation.duration_ms > 0
    assert observation.metadata.get("telemetry") is not None

    telemetry = observation.metadata["telemetry"]
    assert telemetry["tool_name"] == "calculator"
    assert telemetry["status"] == "completed"
    assert telemetry["input_size_bytes"] > 0
    assert telemetry["output_size_bytes"] > 0

    # Verify events
    events = emitter.get_events_for_run(run_id)
    assert len(events) == 3
    assert events[0].event_type == ExecutionEventType.TOOL_CALL_REQUESTED
    assert events[1].event_type == ExecutionEventType.TOOL_CALL_STARTED
    assert events[2].event_type == ExecutionEventType.TOOL_CALL_COMPLETED
    assert [e.sequence_number for e in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_executor_missing_tool():
    executor = ToolExecutor(registry=ToolRegistry())
    invocation = ToolInvocation(
        tool_name="non_existent_tool",
        arguments={},
    )
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.REJECTED
    assert "not registered" in (observation.error or "")


@pytest.mark.asyncio
async def test_executor_validation_failure():
    executor = ToolExecutor()
    invocation = ToolInvocation(
        tool_name="calculator",
        arguments={"expression": 99999},  # Wrong type
    )
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.REJECTED
    assert "Invalid type" in (observation.error or "")


@pytest.mark.asyncio
async def test_executor_policy_rejection_for_dangerous_tool():
    class DangerousTool(BaseTool):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="dangerous_tool",
                description="Simulated dangerous tool",
                input_schema={"type": "object"},
                policy_level=ToolPolicyClassification.DANGEROUS,
            )

        async def execute(self, arguments):
            return {}

    registry = ToolRegistry()
    registry.register(DangerousTool())
    executor = ToolExecutor(registry=registry)

    invocation = ToolInvocation(tool_name="dangerous_tool", arguments={})
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.REJECTED
    assert "prohibited by current security policy" in (observation.error or "")


@pytest.mark.asyncio
async def test_executor_policy_rejection_for_disabled_tool():
    class DisabledTool(BaseTool):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="disabled_tool",
                description="Disabled tool",
                input_schema={"type": "object"},
                enabled=False,
                policy_level=ToolPolicyClassification.SAFE,
            )

        async def execute(self, arguments):
            return {}

    registry = ToolRegistry()
    registry.register(DisabledTool())
    executor = ToolExecutor(registry=registry)

    invocation = ToolInvocation(tool_name="disabled_tool", arguments={})
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.REJECTED
    assert "is currently disabled" in (observation.error or "")


@pytest.mark.asyncio
async def test_executor_timeout_boundary():
    class SlowTool(BaseTool):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="slow_tool",
                description="Tool that simulates hanging execution",
                input_schema={"type": "object"},
                timeout_seconds=0.01,
                policy_level=ToolPolicyClassification.SAFE,
            )

        async def execute(self, arguments):
            await asyncio.sleep(0.5)
            return {"status": "done"}

    registry = ToolRegistry()
    registry.register(SlowTool())
    emitter = EventEmitter()
    executor = ToolExecutor(registry=registry, emitter=emitter)

    run_id = uuid.uuid4()
    invocation = ToolInvocation(tool_name="slow_tool", arguments={}, run_id=run_id)
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.TIMEOUT
    assert "timed out after" in (observation.error or "")

    events = emitter.get_events_for_run(run_id)
    assert events[-1].event_type == ExecutionEventType.TOOL_CALL_TIMEOUT


@pytest.mark.asyncio
async def test_executor_tool_execution_error():
    executor = ToolExecutor()
    invocation = ToolInvocation(
        tool_name="calculator",
        arguments={"expression": "10 / 0"},
    )
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.FAILED
    assert "Division by zero" in (observation.error or "")


@pytest.mark.asyncio
async def test_executor_unexpected_exception_isolation():
    class CrashingTool(BaseTool):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="crashing_tool",
                description="Simulates unexpected runtime error",
                input_schema={"type": "object"},
                policy_level=ToolPolicyClassification.SAFE,
            )

        async def execute(self, arguments):
            raise RuntimeError("Unexpected internal crash simulation")

    registry = ToolRegistry()
    registry.register(CrashingTool())
    executor = ToolExecutor(registry=registry)

    invocation = ToolInvocation(tool_name="crashing_tool", arguments={})
    # Must NOT crash the process
    observation = await executor.execute(invocation)

    assert observation.success is False
    assert observation.status == InvocationStatus.FAILED
    assert "RuntimeError" in (observation.error or "")
