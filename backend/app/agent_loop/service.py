"""Application service orchestrating Autonomous Agent Loop lifecycle, security, and persistence."""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.budget import AgentBudget
from app.agent_loop.controller import AgentController
from app.agent_loop.errors import AgentLoopError, AgentLoopNotFoundError
from app.agent_loop.iteration import AgentIterationRunner
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.repository import AgentLoopRepository
from app.agent_loop.schemas import (
    AgentBudgetResponse,
    AgentBudgetState,
    AgentIterationResponse,
    AgentLoopCreateRequest,
    AgentLoopResponse,
    AgentLoopResumeRequest,
    AgentLoopState,
    AgentLoopStatus,
    AutonomyLevel,
)
from app.core.logging import get_logger
from app.db.models.event import ExecutionEventModel
from app.db.models.loop import AgentLoopModel
from app.db.models.task import Task
from app.evaluation.service import EvaluationService
from app.llm.base import LLMProvider
from app.memory.service import MemoryService
from app.observability.events import EventEmitter
from app.planner.service import PlannerService
from app.schemas.event import ExecutionEvent, ExecutionEventType

logger = get_logger("aegis.agent_loop.service")


class AgentLoopService:
    """
    Application boundary for the Controlled Autonomous Agent Loop subsystem.
    Enforces multi-tenant ownership, budget limits, idempotency, and audit trails.
    """

    def __init__(
        self,
        planner_service: PlannerService | None = None,
        evaluation_service: EvaluationService | None = None,
        memory_service: MemoryService | None = None,
        llm_provider: LLMProvider | None = None,
        policy: AgentLoopPolicy | None = None,
        event_emitter: EventEmitter | None = None,
        repository: AgentLoopRepository | None = None,
    ) -> None:
        self.policy = policy or AgentLoopPolicy()
        self.event_emitter = event_emitter or EventEmitter()
        self.repository = repository or AgentLoopRepository()
        self.planner_service = planner_service or PlannerService(
            llm_provider=llm_provider,
            memory_service=memory_service,
            event_emitter=self.event_emitter,
        )
        self.evaluation_service = evaluation_service or EvaluationService(
            llm_provider=llm_provider,
            memory_service=memory_service,
            event_emitter=self.event_emitter,
        )
        self.memory_service = memory_service

        # Iteration runner and controller
        self.iteration_runner = AgentIterationRunner(
            planner_service=self.planner_service,
            evaluation_service=self.evaluation_service,
            memory_service=self.memory_service,
            policy=self.policy,
            event_emitter=self.event_emitter,
        )
        self.controller = AgentController(
            iteration_runner=self.iteration_runner,
            policy=self.policy,
            event_emitter=self.event_emitter,
        )

        # In-memory active cancellation tokens per loop_id
        self._cancellation_tokens: dict[uuid.UUID, asyncio.Event] = {}

    async def _verify_task_ownership(
        self,
        task_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> Task:
        """Verify task exists and belongs to the authenticated user."""
        stmt = select(Task).where(Task.id == task_id, Task.user_id == trusted_user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()
        if not task:
            raise AgentLoopNotFoundError(f"Task '{task_id}' not found for user.")
        return task

    async def _get_loop_and_verify_ownership(
        self,
        loop_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentLoopModel:
        """Retrieve loop model and enforce tenant boundary at database query level."""
        loop_model = await self.repository.get_loop(loop_id, session, user_id=trusted_user_id)
        if not loop_model:
            raise AgentLoopNotFoundError(f"Agent loop '{loop_id}' not found.")
        return loop_model

    def _to_response(self, model: AgentLoopModel) -> AgentLoopResponse:
        """Convert database model to response schema."""
        raw_final = (
            model.final_result.get("result")
            if isinstance(model.final_result, dict)
            else model.final_result
        )
        return AgentLoopResponse(
            loop_id=model.id,
            task_id=model.task_id,
            run_id=model.run_id,
            objective=model.objective,
            iteration_number=model.iteration_number,
            status=AgentLoopStatus(model.status),
            current_plan_id=None,
            final_result=raw_final,
            budget=AgentBudgetState(**model.budget),
            started_at=model.started_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
            metadata=model.loop_metadata,
        )

    async def create_and_start_loop(
        self,
        request: AgentLoopCreateRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentLoopResponse:
        """
        Create, persist, and run a bounded autonomous agent loop.
        Supports idempotency keys to prevent duplicate executions.
        """
        await self._verify_task_ownership(request.task_id, trusted_user_id, session)

        # Idempotency check
        if request.idempotency_key:
            existing = await self.repository.get_by_idempotency_key(
                request.idempotency_key, trusted_user_id, session
            )
            if existing:
                logger.info(f"Idempotent loop match found for key '{request.idempotency_key}'")
                return self._to_response(existing)

        loop_id = uuid.uuid4()
        loop_state = AgentLoopState(
            loop_id=loop_id,
            task_id=request.task_id,
            run_id=request.run_id,
            user_id=trusted_user_id,
            objective=request.objective,
            autonomy_level=request.autonomy_level,
            metadata=request.metadata,
        )

        # Persist initial record
        model = await self.repository.create_loop(
            loop_state=loop_state,
            autonomy_level=request.autonomy_level,
            idempotency_key=request.idempotency_key,
            session=session,
        )

        await self.event_emitter.emit(
            task_id=request.task_id,
            run_id=request.run_id,
            event_type=ExecutionEventType.AGENT_LOOP_CREATED,
            payload={
                "loop_id": str(loop_id),
                "objective": request.objective,
                "autonomy_level": request.autonomy_level.value,
            },
            session=session,
        )

        # Register cancellation token
        cancel_token = asyncio.Event()
        self._cancellation_tokens[loop_id] = cancel_token

        # Run loop
        try:
            loop_state = await self.controller.run_loop(
                loop_state=loop_state,
                autonomy_level=request.autonomy_level,
                cancellation_token=cancel_token,
                session=session,
            )
        finally:
            self._cancellation_tokens.pop(loop_id, None)
            await self.repository.save_loop_state(loop_state, session)
            await session.commit()

        updated_model = await self.repository.get_loop(loop_id, session)
        return self._to_response(updated_model or model)

    async def get_loop(
        self,
        loop_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentLoopResponse:
        """Fetch status and outcome of an agent loop."""
        model = await self._get_loop_and_verify_ownership(loop_id, trusted_user_id, session)
        return self._to_response(model)

    async def resume_loop(
        self,
        loop_id: uuid.UUID,
        request: AgentLoopResumeRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentLoopResponse:
        """
        Resume execution from latest checkpoint state.
        """
        model = await self._get_loop_and_verify_ownership(loop_id, trusted_user_id, session)

        if model.status == AgentLoopStatus.SAFETY_STOPPED.value:
            raise AgentLoopError(
                "Cannot resume a safety-stopped loop without explicit administrative clearance."
            )

        if model.status == AgentLoopStatus.COMPLETED.value:
            return self._to_response(model)

        budget_state = AgentBudgetState(**model.budget)
        if request.override_budget:
            budget_state.iterations = 0

        raw_final = (
            model.final_result.get("result")
            if isinstance(model.final_result, dict)
            else model.final_result
        )
        loop_state = AgentLoopState(
            loop_id=model.id,
            task_id=model.task_id,
            run_id=model.run_id,
            user_id=trusted_user_id,
            objective=model.objective,
            iteration_number=model.iteration_number,
            status=AgentLoopStatus.WAITING,
            final_result=raw_final,
            budget=budget_state,
            metadata=model.loop_metadata,
        )

        await self.event_emitter.emit(
            task_id=model.task_id,
            run_id=model.run_id,
            event_type=ExecutionEventType.AGENT_LOOP_RESUMED,
            payload={"loop_id": str(loop_id), "iteration": model.iteration_number},
            session=session,
        )

        cancel_token = asyncio.Event()
        self._cancellation_tokens[loop_id] = cancel_token

        try:
            loop_state = await self.controller.run_loop(
                loop_state=loop_state,
                autonomy_level=AutonomyLevel(model.autonomy_level),
                cancellation_token=cancel_token,
                session=session,
            )
        finally:
            self._cancellation_tokens.pop(loop_id, None)
            await self.repository.save_loop_state(loop_state, session)
            await session.commit()

        updated = await self.repository.get_loop(loop_id, session)
        return self._to_response(updated or model)

    async def cancel_loop(
        self,
        loop_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentLoopResponse:
        """Cancel an in-flight or waiting agent loop."""
        model = await self._get_loop_and_verify_ownership(loop_id, trusted_user_id, session)

        token = self._cancellation_tokens.get(loop_id)
        if token:
            token.set()

        model.status = AgentLoopStatus.CANCELLED.value
        await session.commit()

        await self.event_emitter.emit(
            task_id=model.task_id,
            run_id=model.run_id,
            event_type=ExecutionEventType.AGENT_LOOP_CANCELLED,
            payload={"loop_id": str(loop_id)},
            session=session,
        )

        return self._to_response(model)

    async def get_iterations(
        self,
        loop_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[AgentIterationResponse]:
        """Fetch all iteration audit records for an agent loop."""
        await self._get_loop_and_verify_ownership(loop_id, trusted_user_id, session)
        records = await self.repository.get_iterations(loop_id, session, user_id=trusted_user_id)
        return [
            AgentIterationResponse(
                iteration_id=r.id,
                loop_id=r.loop_id,
                iteration_number=r.iteration_number,
                status=AgentLoopStatus(r.status),
                plan_id=r.plan_id,
                evaluation_id=r.evaluation_id,
                reflection_id=r.reflection_id,
                started_at=r.started_at,
                completed_at=r.completed_at,
                error=r.error,
            )
            for r in records
        ]

    async def get_budget(
        self,
        loop_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentBudgetResponse:
        """Fetch resource budget status and remaining allowances."""
        model = await self._get_loop_and_verify_ownership(loop_id, trusted_user_id, session)
        budget_state = AgentBudgetState(**model.budget)
        budget_mgr = AgentBudget(policy=self.policy, state=budget_state)

        limits = {
            "max_iterations": self.policy.max_iterations,
            "max_tool_calls": self.policy.max_tool_calls,
            "max_llm_calls": self.policy.max_llm_calls,
            "max_retries": self.policy.max_total_retries,
            "max_memory_reads": self.policy.max_memory_retrievals,
            "max_memory_writes": self.policy.max_memory_writes,
            "max_plan_executions": self.policy.max_plan_executions,
        }

        return AgentBudgetResponse(
            loop_id=loop_id,
            budget=budget_state,
            limits=limits,
            remaining=budget_mgr.get_remaining_budget(),
        )

    async def get_events(
        self,
        loop_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[ExecutionEvent]:
        """Retrieve monotonic execution events associated with the loop run."""
        model = await self._get_loop_and_verify_ownership(loop_id, trusted_user_id, session)
        stmt = (
            select(ExecutionEventModel)
            .where(ExecutionEventModel.run_id == model.run_id)
            .order_by(ExecutionEventModel.sequence_number.asc())
        )
        res = await session.execute(stmt)
        event_models = res.scalars().all()
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
            for e in event_models
        ]
