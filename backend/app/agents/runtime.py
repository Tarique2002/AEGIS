"""Agent Runtime: Foundational stateful runtime orchestrator for AEGIS."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.observability.events import EventEmitter
from app.schemas.common import ChatMessage, ChatRole, RunType, TaskStatus, utc_now
from app.schemas.event import ExecutionEventType
from app.schemas.response import AgentResponseModel
from app.schemas.state import AgentState
from app.schemas.telemetry import TelemetryData

logger = get_logger("aegis.agents.runtime")


class AgentRuntime:
    """
    AEGIS Stateful Agent Runtime.
    Manages state initialization, LLM provider invocation, lifecycle transitions,
    event sequencing, and transactional PostgreSQL persistence.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self.provider = provider or get_llm_provider()
        self.emitter = emitter or EventEmitter()

    async def execute_task(
        self,
        objective: str,
        session: AsyncSession,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentState:
        """
        Execute a single foundational agent pass for the given objective.
        Ensures strict monotonic event sequencing, telemetry recording, and state persistence.
        """
        task_uuid = task_id or uuid.uuid4()
        run_uuid = uuid.uuid4()
        task_meta = metadata or {}

        # 1. Initialize Strongly Typed Agent State
        state = AgentState(
            task_id=task_uuid,
            run_id=run_uuid,
            user_id=user_id,
            objective=objective,
            status=TaskStatus.PENDING,
            metadata=task_meta,
        )

        # 2. Ensure Task record exists in PostgreSQL
        stmt = select(Task).where(Task.id == task_uuid)
        result = await session.execute(stmt)
        task_model = result.scalar_one_or_none()

        if not task_model:
            task_model = Task(
                id=task_uuid,
                user_id=user_id,
                objective=objective,
                status=TaskStatus.PENDING.value,
                task_metadata=task_meta,
            )
            session.add(task_model)
            await session.flush()
            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.TASK_CREATED,
                payload={"objective": objective, "user_id": str(user_id) if user_id else None},
                session=session,
            )

        # 3. Create AgentRun Record
        provider_meta = self.provider.metadata()
        run_model = AgentRun(
            id=run_uuid,
            task_id=task_uuid,
            run_type=RunType.EXECUTION.value,
            status=TaskStatus.RUNNING.value,
            model_used=provider_meta.model_name,
            started_at=utc_now(),
        )
        session.add(run_model)
        await session.flush()

        await self.emitter.emit(
            task_id=task_uuid,
            run_id=run_uuid,
            event_type=ExecutionEventType.RUN_STARTED,
            payload={"run_type": RunType.EXECUTION.value, "model": provider_meta.model_name},
            session=session,
        )

        # 4. State Transition: PENDING -> RUNNING
        state.transition_to(TaskStatus.RUNNING)
        task_model.status = TaskStatus.RUNNING.value

        await self.emitter.emit(
            task_id=task_uuid,
            run_id=run_uuid,
            event_type=ExecutionEventType.STATE_TRANSITION,
            payload={
                "from_status": TaskStatus.PENDING.value,
                "to_status": TaskStatus.RUNNING.value,
            },
            session=session,
        )

        # 5. Prepare Model Inputs
        system_message = ChatMessage(
            role=ChatRole.SYSTEM,
            content=(
                "You are AEGIS, an enterprise autonomous AI agent runtime. "
                "Provide a clear, accurate, and structured response."
            ),
        )

        user_message = ChatMessage(
            role=ChatRole.USER,
            content=objective,
        )
        state.messages = [system_message, user_message]

        # 6. Execute Model Call
        await self.emitter.emit(
            task_id=task_uuid,
            run_id=run_uuid,
            event_type=ExecutionEventType.MODEL_CALL_STARTED,
            payload={"provider": provider_meta.provider_name, "model": provider_meta.model_name},
            session=session,
        )

        call_start = utc_now()
        try:
            structured_resp = await self.provider.generate_structured(
                messages=state.messages,
                response_model=AgentResponseModel,
            )
            call_end = utc_now()
            duration_ms = structured_resp.duration_ms or (
                (call_end - call_start).total_seconds() * 1000.0
            )

            # 7. Collect Execution Telemetry (real metrics only)
            telemetry = TelemetryData(
                start_time=call_start,
                end_time=call_end,
                duration_ms=duration_ms,
                provider=provider_meta.provider_name,
                model=structured_resp.model or provider_meta.model_name,
                prompt_tokens=structured_resp.prompt_tokens,
                completion_tokens=structured_resp.completion_tokens,
                total_tokens=structured_resp.total_tokens,
                estimated_cost_usd=None,
            )
            state.telemetry = telemetry
            if structured_resp.total_tokens is not None:
                state.usage.prompt_tokens = structured_resp.prompt_tokens or 0
                state.usage.completion_tokens = structured_resp.completion_tokens or 0
                state.usage.total_tokens = structured_resp.total_tokens

            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.MODEL_CALL_COMPLETED,
                payload={
                    "duration_ms": duration_ms,
                    "prompt_tokens": structured_resp.prompt_tokens,
                    "completion_tokens": structured_resp.completion_tokens,
                    "total_tokens": structured_resp.total_tokens,
                    "is_completed": structured_resp.data.is_completed,
                },
                session=session,
            )

            # 8. Update State with Assistant Output
            assistant_message = ChatMessage(
                role=ChatRole.ASSISTANT,
                content=structured_resp.data.response_text,
            )
            state.messages.append(assistant_message)
            state.final_result = structured_resp.data.response_text

            # 9. State Transition: RUNNING -> COMPLETED
            state.transition_to(TaskStatus.COMPLETED)

            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.STATE_TRANSITION,
                payload={
                    "from_status": TaskStatus.RUNNING.value,
                    "to_status": TaskStatus.COMPLETED.value,
                },
                session=session,
            )

            # 10. Persist Completion to Database
            task_model.status = TaskStatus.COMPLETED.value
            task_model.result = state.final_result
            task_model.completed_at = state.completed_at

            run_model.status = TaskStatus.COMPLETED.value
            run_model.result = state.final_result
            run_model.latency_ms = duration_ms
            run_model.prompt_tokens = structured_resp.prompt_tokens or 0
            run_model.completion_tokens = structured_resp.completion_tokens or 0
            run_model.total_tokens = structured_resp.total_tokens or 0
            run_model.ended_at = call_end
            run_model.state_snapshot = state.model_dump(mode="json")

            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.RUN_COMPLETED,
                payload={"status": TaskStatus.COMPLETED.value},
                session=session,
            )
            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.TASK_COMPLETED,
                payload={"status": TaskStatus.COMPLETED.value},
                session=session,
            )

            await session.commit()
            return state

        except Exception as exc:
            call_end = utc_now()
            duration_ms = (call_end - call_start).total_seconds() * 1000.0
            error_message = str(exc)

            logger.error(
                f"AgentRuntime failure for Task {task_uuid} / Run {run_uuid}: {error_message}",
                exc_info=True,
            )

            state.errors.append(error_message)
            try:
                state.transition_to(TaskStatus.FAILED)
            except Exception:
                state.status = TaskStatus.FAILED
                state.completed_at = call_end

            # Emit failure events
            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.RUN_FAILED,
                payload={"error": error_message},
                session=session,
            )
            await self.emitter.emit(
                task_id=task_uuid,
                run_id=run_uuid,
                event_type=ExecutionEventType.TASK_FAILED,
                payload={"error": error_message},
                session=session,
            )

            # Persist failure in PostgreSQL
            task_model.status = TaskStatus.FAILED.value
            task_model.completed_at = call_end

            run_model.status = TaskStatus.FAILED.value
            run_model.error = error_message
            run_model.latency_ms = duration_ms
            run_model.ended_at = call_end
            run_model.state_snapshot = state.model_dump(mode="json")

            await session.commit()
            raise
