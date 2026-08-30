"""
End-to-end verification script for AEGIS Phase 2 (Tools & Security Engine).
Demonstrates:
1. Tool discovery from ToolRegistry
2. Successful tool execution of (25 * 4) + 10 through the full pipeline
3. Observation and AgentState recording
4. Sequential event emission and monotonic sequence numbering
5. Security failure rejection for malicious/unsafe payloads
"""

import asyncio
import json
import uuid

from app.observability.events import EventEmitter
from app.schemas.common import TaskStatus
from app.schemas.state import AgentState
from app.tools.executor import ToolExecutor
from app.tools.registry import create_default_tool_registry
from app.tools.schemas import InvocationStatus, ToolInvocation
from app.tools.service import ToolService


async def main():
    print("=================================================================")
    print("           AEGIS PHASE 2 END-TO-END VERIFICATION               ")
    print("=================================================================\n")

    registry = create_default_tool_registry()
    emitter = EventEmitter()
    executor = ToolExecutor(registry=registry, emitter=emitter)
    service = ToolService(registry=registry, executor=executor)

    # 1. Tool Discovery
    print("1. Discovering Registered Tools:")
    tools = service.list_tools()
    for t in tools:
        print(
            f"   - Tool: {t.name} (v{t.version}) | Policy: {t.policy_level.value} "
            f"| Timeout: {t.timeout_seconds}s"
        )

        print(f"     Description: {t.description}")
        print(f"     Capabilities: {t.capabilities}")

    print("\n-----------------------------------------------------------------")
    print("2. Scenario 1: Safe Calculation ((25 * 4) + 10):")
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    state = AgentState(
        task_id=task_id,
        run_id=run_id,
        objective="Perform arithmetic verification",
        status=TaskStatus.RUNNING,
    )

    invocation = ToolInvocation(
        tool_name="calculator",
        arguments={"expression": "(25 * 4) + 10"},
        task_id=task_id,
        run_id=run_id,
    )

    observation = await service.execute_tool(invocation)
    state.record_tool_execution(invocation, observation)

    print(f"   Invocation Status: {invocation.status.value}")
    print(f"   Observation Success: {observation.success}")
    print(f"   Observation Status: {observation.status.value}")
    print(f"   Computed Output: {json.dumps(observation.output)}")
    print(f"   Duration: {observation.duration_ms:.2f} ms")
    print(f"   Telemetry: {observation.metadata.get('telemetry')}")

    print("\n   AgentState updated:")
    print(f"   - Total tool calls in state: {len(state.tool_calls)}")
    print(f"   - Total observations in state: {len(state.observations)}")
    print(f"   - Observation matches result: {state.observations[0].output.get('result') == 110}")

    print("\n   Execution Event Sequence:")
    events = emitter.get_events_for_run(run_id)
    for evt in events:
        print(f"   [{evt.sequence_number}] {evt.event_type.value} -> payload={evt.payload}")

    assert observation.success is True
    assert observation.output["result"] == 110
    assert len(events) == 3

    print("\n-----------------------------------------------------------------")
    print("3. Scenario 2: Security Rejection of Arbitrary Python / System Call:")
    unsafe_inv = ToolInvocation(
        tool_name="calculator",
        arguments={"expression": "__import__('os').system('ls -la')"},
        task_id=task_id,
        run_id=run_id,
    )

    unsafe_obs = await service.execute_tool(unsafe_inv)
    state.record_tool_execution(unsafe_inv, unsafe_obs)

    print(f"   Invocation Status: {unsafe_inv.status.value}")
    print(f"   Observation Success: {unsafe_obs.success}")
    print(f"   Observation Status: {unsafe_obs.status.value}")
    print(f"   Safe Error Returned: {unsafe_obs.error}")
    print("   Process Alive & Stable: TRUE")

    assert unsafe_obs.success is False
    assert unsafe_obs.status == InvocationStatus.REJECTED

    print("\n=================================================================")
    print("   [SUCCESS] ALL PHASE 2 VERIFICATION SCENARIOS PASSED SAFELY!   ")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())
