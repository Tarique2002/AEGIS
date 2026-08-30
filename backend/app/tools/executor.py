"""
Secure Tool Execution Engine with timeout enforcement, policy checks, and exception boundaries.
"""

import asyncio
import json
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.observability.events import EventEmitter
from app.schemas.common import utc_now
from app.schemas.event import ExecutionEventType
from app.tools.errors import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPolicyViolationError,
    ToolValidationError,
)
from app.tools.policies import ToolPolicy
from app.tools.registry import ToolRegistry, create_default_tool_registry
from app.tools.schemas import InvocationStatus, ToolInvocation, ToolObservation, ToolTelemetry

logger = get_logger("aegis.tools.executor")


class ToolExecutor:
    """
    AEGIS Secure Tool Executor.
    Coordinates registry lookup, parameter validation, security policy enforcement,
    async timeout boundaries, structured observation generation, and trace events.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy: ToolPolicy | None = None,
        emitter: EventEmitter | None = None,
        safety_gate: Any | None = None,
    ) -> None:
        self.registry = registry or create_default_tool_registry()
        self.policy = policy or ToolPolicy()
        self.emitter = emitter or EventEmitter()
        self.safety_gate = safety_gate

    async def execute(
        self,
        invocation: ToolInvocation,
        session: AsyncSession | None = None,
    ) -> ToolObservation:
        """
        Execute a tool invocation within a safe execution and exception boundary.
        Guarantees that tool exceptions will not crash the host process and produces
        a structured ToolObservation.
        """
        start_time = time.perf_counter()
        utc_start = utc_now()
        task_id = invocation.task_id or uuid.uuid4()
        run_id = invocation.run_id or uuid.uuid4()

        # Calculate input size
        input_size_bytes = 0
        try:
            input_size_bytes = len(json.dumps(invocation.arguments).encode("utf-8"))
        except Exception:
            pass

        # 1. Resolve Tool from Registry
        try:
            tool = self.registry.get(invocation.tool_name)
        except ToolNotFoundError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.REJECTED
            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_REJECTED,
                payload={"tool_name": invocation.tool_name, "reason": exc.message},
                session=session,
            )
            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.REJECTED,
                success=False,
                error=exc.message,
                duration_ms=duration_ms,
            )

        tool_def = tool.definition

        # 2. Security Policy Validation
        try:
            self.policy.validate_invocation(tool_def, invocation)
        except ToolPolicyViolationError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.REJECTED
            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_REJECTED,
                payload={"tool_name": invocation.tool_name, "reason": exc.message},
                session=session,
            )
            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.REJECTED,
                success=False,
                error=exc.message,
                duration_ms=duration_ms,
            )

        # 2b. Safety Gate Evaluation (Phase 8)
        if self.safety_gate:
            from app.safety.schemas import SafetyContext

            user_id = getattr(invocation, "user_id", None) or uuid.UUID(
                "00000000-0000-0000-0000-000000000001"
            )
            s_ctx = SafetyContext(
                user_id=user_id,
                task_id=task_id,
                run_id=run_id,
                tool_name=invocation.tool_name,
                action=f"execute_tool_{invocation.tool_name}",
                arguments_metadata=invocation.arguments,
            )
            decision = await self.safety_gate.evaluate(s_ctx)
            if not decision.allowed:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                invocation.status = InvocationStatus.REJECTED
                await self._emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    event_type=ExecutionEventType.TOOL_CALL_REJECTED,
                    payload={"tool_name": invocation.tool_name, "reason": decision.reason},
                    session=session,
                )
                return ToolObservation(
                    invocation_id=invocation.invocation_id,
                    tool_name=invocation.tool_name,
                    status=InvocationStatus.REJECTED,
                    success=False,
                    error=f"Safety Gate Denied: {decision.reason}",
                    duration_ms=duration_ms,
                )

        # 3. Parameter Validation
        try:
            validated_args = tool.validate_arguments(invocation.arguments)
        except ToolValidationError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.REJECTED
            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_REJECTED,
                payload={"tool_name": invocation.tool_name, "reason": exc.message},
                session=session,
            )
            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.REJECTED,
                success=False,
                error=exc.message,
                duration_ms=duration_ms,
            )

        # 4. Emit TOOL_CALL_REQUESTED & TOOL_CALL_STARTED
        await self._emit_event(
            task_id=task_id,
            run_id=run_id,
            event_type=ExecutionEventType.TOOL_CALL_REQUESTED,
            payload={
                "tool_name": invocation.tool_name,
                "invocation_id": str(invocation.invocation_id),
            },
            session=session,
        )

        invocation.status = InvocationStatus.RUNNING

        await self._emit_event(
            task_id=task_id,
            run_id=run_id,
            event_type=ExecutionEventType.TOOL_CALL_STARTED,
            payload={
                "tool_name": invocation.tool_name,
                "timeout_seconds": tool_def.timeout_seconds,
            },
            session=session,
        )

        # 5. Execute with Timeout Boundary
        try:
            output = await asyncio.wait_for(
                tool.execute(validated_args),
                timeout=tool_def.timeout_seconds,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            utc_end = utc_now()
            invocation.status = InvocationStatus.COMPLETED

            # Calculate output size
            output_size_bytes = 0
            try:
                output_size_bytes = len(json.dumps(output).encode("utf-8"))
            except Exception:
                pass

            telemetry = ToolTelemetry(
                start_time=utc_start,
                end_time=utc_end,
                duration_ms=duration_ms,
                tool_name=tool_def.name,
                tool_version=tool_def.version,
                status=InvocationStatus.COMPLETED,
                input_size_bytes=input_size_bytes,
                output_size_bytes=output_size_bytes,
            )

            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_COMPLETED,
                payload={
                    "tool_name": invocation.tool_name,
                    "duration_ms": duration_ms,
                    "output_size_bytes": output_size_bytes,
                },
                session=session,
            )

            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.COMPLETED,
                success=True,
                output=output,
                duration_ms=duration_ms,
                metadata={"telemetry": telemetry.model_dump(mode="json")},
            )

        except TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.TIMEOUT
            error_msg = (
                f"Tool '{invocation.tool_name}' timed out after " f"{tool_def.timeout_seconds}s."
            )

            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_TIMEOUT,
                payload={
                    "tool_name": invocation.tool_name,
                    "timeout_seconds": tool_def.timeout_seconds,
                },
                session=session,
            )

            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.TIMEOUT,
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
            )

        except (ToolValidationError, ToolPolicyViolationError) as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.REJECTED

            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_REJECTED,
                payload={"tool_name": invocation.tool_name, "reason": exc.message},
                session=session,
            )

            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.REJECTED,
                success=False,
                error=exc.message,
                duration_ms=duration_ms,
            )

        except ToolExecutionError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.FAILED

            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_FAILED,
                payload={"tool_name": invocation.tool_name, "error": exc.message},
                session=session,
            )

            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.FAILED,
                success=False,
                error=exc.message,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            # Unexpected exception boundary: log safely and prevent process crash
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            invocation.status = InvocationStatus.FAILED
            logger.exception(
                f"Unexpected error executing tool '{invocation.tool_name}': {str(exc)}",
                extra={"invocation_id": str(invocation.invocation_id)},
            )

            safe_error_msg = f"Tool execution failed: {type(exc).__name__} - {str(exc)}"

            await self._emit_event(
                task_id=task_id,
                run_id=run_id,
                event_type=ExecutionEventType.TOOL_CALL_FAILED,
                payload={"tool_name": invocation.tool_name, "error": safe_error_msg},
                session=session,
            )

            return ToolObservation(
                invocation_id=invocation.invocation_id,
                tool_name=invocation.tool_name,
                status=InvocationStatus.FAILED,
                success=False,
                error=safe_error_msg,
                duration_ms=duration_ms,
            )

    async def _emit_event(
        self,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        event_type: ExecutionEventType,
        payload: dict,
        session: AsyncSession | None,
    ) -> None:
        await self.emitter.emit(
            task_id=task_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            session=session,
        )
