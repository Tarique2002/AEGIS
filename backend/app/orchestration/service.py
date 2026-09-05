"""OrchestrationService providing multi-tenant isolation, idempotency, and lifecycle management."""

import asyncio
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.service import AgentLoopService
from app.core.errors import OrchestrationNotFoundError
from app.core.logging import get_logger
from app.db.models.orchestration import OrchestrationModel
from app.db.models.task import Task
from app.evaluation.service import EvaluationService
from app.memory.service import MemoryService
from app.observability.events import EventEmitter
from app.orchestration.orchestrator import MultiAgentOrchestrator
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.repository import OrchestrationRepository
from app.orchestration.schemas import (
    DelegatedTaskStatus,
    OrchestrationBudgetResponse,
    OrchestrationBudgetState,
    OrchestrationCreateRequest,
    OrchestrationResponse,
    OrchestrationResumeRequest,
    OrchestrationStatus,
    WorkerStateResponse,
    WorkerType,
)
from app.schemas.event import ExecutionEvent, ExecutionEventType

logger = get_logger(__name__)


class OrchestrationService:
    """Service handling multi-agent orchestration lifecycle, tenant security, and event tracing."""

    def __init__(
        self,
        repository: OrchestrationRepository | None = None,
        event_emitter: EventEmitter | None = None,
        agent_loop_service: AgentLoopService | None = None,
        evaluation_service: EvaluationService | None = None,
        memory_service: MemoryService | None = None,
        policy: OrchestrationPolicy | None = None,
    ) -> None:
        self.repository = repository or OrchestrationRepository()
        self.event_emitter = event_emitter or EventEmitter()
        self.agent_loop_service = agent_loop_service or AgentLoopService(
            event_emitter=self.event_emitter
        )
        self.evaluation_service = evaluation_service
        self.memory_service = memory_service
        self.policy = policy or OrchestrationPolicy()

        self.orchestrator = MultiAgentOrchestrator(
            agent_loop_service=self.agent_loop_service,
            evaluation_service=self.evaluation_service,
            memory_service=self.memory_service,
            policy=self.policy,
        )

        # In-memory cancellation signals: orchestration_id -> asyncio.Event
        self._cancellation_tokens: dict[uuid.UUID, asyncio.Event] = {}

    async def _verify_task_ownership(
        self, task_id: uuid.UUID, trusted_user_id: uuid.UUID, session: AsyncSession
    ) -> Task:
        """Verify task exists and belongs to the authenticated user."""
        stmt = select(Task).where(Task.id == task_id, Task.user_id == trusted_user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()
        if not task:
            raise OrchestrationNotFoundError(f"Task '{task_id}' not found.")
        return task

    async def _get_orchestration_and_verify_ownership(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationModel:
        """Retrieve orchestration model and enforce tenant boundary."""
        model = await self.repository.get_orchestration(
            orchestration_id, session, user_id=trusted_user_id
        )
        if not model:
            raise OrchestrationNotFoundError(
                f"Orchestration session '{orchestration_id}' not found."
            )
        return model

    def _to_response(self, model: OrchestrationModel) -> OrchestrationResponse:
        """Convert database model to response schema."""
        raw_final = (
            model.final_result.get("final_output")
            if isinstance(model.final_result, dict)
            else model.final_result
        )
        tasks_count = len(model.delegated_tasks) if model.delegated_tasks else 0
        completed_count = sum(1 for t in (model.delegated_tasks or []) if t.status == "COMPLETED")
        return OrchestrationResponse(
            orchestration_id=model.id,
            task_id=model.task_id,
            run_id=model.run_id,
            objective=model.objective,
            status=OrchestrationStatus(model.status),
            plan_id=model.delegation_plan_id,
            tasks_count=tasks_count,
            completed_tasks_count=completed_count,
            final_output=raw_final,
            budget=OrchestrationBudgetState(**model.budget),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error=model.error,
            metadata=model.orchestration_metadata,
        )

    async def run_orchestration(
        self,
        request: OrchestrationCreateRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationResponse:
        """Create, schedule, execute, and persist a multi-agent orchestration session."""
        # 1. Verify Task ownership
        await self._verify_task_ownership(request.task_id, trusted_user_id, session)

        # 2. Check Idempotency Key
        if request.idempotency_key:
            existing = await self.repository.get_by_idempotency_key(
                idempotency_key=request.idempotency_key,
                user_id=trusted_user_id,
                session=session,
            )
            if existing:
                logger.info(
                    f"Returning cached orchestration '{existing.id}' "
                    f"for idempotency key '{request.idempotency_key}'"
                )
                return self._to_response(existing)

        orchestration_id = uuid.uuid4()
        cancellation_token = asyncio.Event()
        self._cancellation_tokens[orchestration_id] = cancellation_token

        # 3. Emit ORCHESTRATION_CREATED
        await self.event_emitter.emit(
            task_id=request.task_id,
            run_id=request.run_id,
            event_type=ExecutionEventType.ORCHESTRATION_CREATED,
            payload={
                "orchestration_id": str(orchestration_id),
                "objective": request.objective,
                "execution_mode": request.execution_mode.value,
            },
            session=session,
        )

        # 4. Execute Orchestrator loop
        state = await self.orchestrator.execute_orchestration(
            orchestration_id=orchestration_id,
            task_id=request.task_id,
            run_id=request.run_id,
            user_id=trusted_user_id,
            objective=request.objective,
            session=session,
            custom_workers=request.workers,
            execution_mode=request.execution_mode,
            max_parallel_workers=request.max_parallel_workers,
            cancellation_token=cancellation_token,
        )

        # 5. Persist to DB
        model = await self.repository.create_orchestration(
            state=state,
            idempotency_key=request.idempotency_key,
            session=session,
        )
        await self.repository.save_orchestration_state(state=state, session=session)
        await session.commit()

        # 6. Emit Completion/Failure event
        final_event = (
            ExecutionEventType.ORCHESTRATION_COMPLETED
            if state.status == OrchestrationStatus.COMPLETED
            else ExecutionEventType.ORCHESTRATION_FAILED
        )
        await self.event_emitter.emit(
            task_id=request.task_id,
            run_id=request.run_id,
            event_type=final_event,
            payload={
                "orchestration_id": str(orchestration_id),
                "status": state.status.value,
                "elapsed_time_ms": state.budget.elapsed_time_ms,
            },
            session=session,
        )

        # 7. Record Multi-Agent Self-Learning Trajectory (Phase 11)
        try:
            from app.learning.schemas import TrajectoryCreate
            from app.learning.service import SelfLearningService

            learning_svc = SelfLearningService(event_emitter=self.event_emitter)
            worker_involvement = [
                {
                    "worker_id": str(w.worker_id),
                    "worker_type": w.worker_type.value,
                    "status": w.status.value,
                    "subtask": w.assigned_subtask,
                    "error": w.error,
                }
                for w in state.workers
            ]
            traj_data = TrajectoryCreate(
                task_id=request.task_id,
                run_id=request.run_id,
                goal=request.objective,
                worker_involvement=worker_involvement,
                final_outcome=state.final_result,
                is_success=(state.status == OrchestrationStatus.COMPLETED),
                duration_ms=float(state.budget.elapsed_time_ms),
            )
            await learning_svc.process_completed_run(
                create_data=traj_data,
                trusted_user_id=trusted_user_id,
                session=session,
                domain="orchestration",
            )
            await session.commit()
        except Exception as exc:
            logger.warning(f"Self-learning processing failed in OrchestrationService: {exc}")

        self._cancellation_tokens.pop(orchestration_id, None)
        return self._to_response(model)

    async def get_orchestration(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationResponse:
        """Fetch orchestration status and summary."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        return self._to_response(model)

    async def get_workers(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[WorkerStateResponse]:
        """Fetch worker task states within an orchestration session."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        return [
            WorkerStateResponse(
                delegated_task_id=t.task_metadata.get("delegated_task_id", str(t.id)),
                worker_id=t.worker_type,
                worker_type=WorkerType(t.worker_type),
                title=t.title,
                status=DelegatedTaskStatus(t.status),
                dependencies=t.dependencies,
                result=t.result,
                error=t.error,
                duration_ms=0.0,
            )
            for t in model.delegated_tasks
        ]

    async def get_results(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Fetch validated worker results and synthesized output."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        return model.final_result or {}

    async def get_events(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[ExecutionEvent]:
        """Fetch monotonic execution event trace for an orchestration run."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        from app.db.models.event import ExecutionEventModel

        stmt = (
            select(ExecutionEventModel)
            .where(ExecutionEventModel.run_id == model.run_id)
            .order_by(ExecutionEventModel.sequence_number.asc())
        )
        res = await session.execute(stmt)
        db_events = res.scalars().all()
        if db_events:
            return [
                ExecutionEvent(
                    event_id=e.id,
                    task_id=e.task_id,
                    run_id=e.run_id,
                    event_type=ExecutionEventType(e.event_type),
                    timestamp=e.timestamp,
                    sequence_number=e.sequence_number,
                    payload=e.payload,
                )
                for e in db_events
            ]
        return self.event_emitter.get_events_for_run(model.run_id)

    async def get_budget(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationBudgetResponse:
        """Fetch resource budget status and remaining limits."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        budget = OrchestrationBudgetState(**model.budget)
        return OrchestrationBudgetResponse(
            orchestration_id=model.id,
            budget=budget,
            limits={
                "max_workers": self.policy.max_workers,
                "max_total_iterations": self.policy.max_total_iterations,
                "max_total_tool_calls": self.policy.max_total_tool_calls,
                "max_total_llm_calls": self.policy.max_total_llm_calls,
                "max_total_execution_seconds": self.policy.max_total_execution_seconds,
            },
            remaining={
                "remaining_iterations": max(
                    0, self.policy.max_total_iterations - budget.total_iterations
                ),
                "remaining_tool_calls": max(
                    0, self.policy.max_total_tool_calls - budget.total_tool_calls
                ),
                "remaining_llm_calls": max(
                    0, self.policy.max_total_llm_calls - budget.total_llm_calls
                ),
            },
        )

    async def cancel_orchestration(
        self,
        orchestration_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationResponse:
        """Signal cooperative cancellation of an actively running orchestration."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        token = self._cancellation_tokens.get(orchestration_id)
        if token:
            token.set()

        model.status = OrchestrationStatus.CANCELLED.value
        await session.commit()

        await self.event_emitter.emit(
            task_id=model.task_id,
            run_id=model.run_id,
            event_type=ExecutionEventType.ORCHESTRATION_CANCELLED,
            payload={"orchestration_id": str(orchestration_id)},
            session=session,
        )
        return self._to_response(model)

    async def resume_orchestration(
        self,
        orchestration_id: uuid.UUID,
        request: OrchestrationResumeRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationResponse:
        """Resume an orchestration session or initiate targeted rework pass."""
        model = await self._get_orchestration_and_verify_ownership(
            orchestration_id, trusted_user_id, session
        )
        req = OrchestrationCreateRequest(
            task_id=model.task_id,
            run_id=model.run_id,
            objective=model.objective,
            metadata=request.metadata,
        )
        return await self.run_orchestration(req, trusted_user_id, session)
