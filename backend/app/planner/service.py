"""Planner Service managing plan lifecycle, DAG validation, graph execution, and checkpointing."""

import asyncio
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PlanNotFoundError
from app.core.logging import get_logger
from app.db.models.task import Task
from app.llm.base import LLMProvider
from app.memory.schemas import MemorySearchQuery
from app.memory.service import MemoryService
from app.observability.events import EventEmitter
from app.planner.checkpoint import CheckpointManager
from app.planner.executor import GraphExecutor
from app.planner.planner import DeterministicPlanner, LLMPlanner
from app.planner.policies import PlannerPolicy
from app.planner.repository import PlannerRepository
from app.planner.schemas import (
    ExecutionContext,
    ExecutionPlan,
    NodeStatus,
    PlanCreateRequest,
    PlanExecuteRequest,
    PlanExecutionResponse,
    PlanNode,
    PlanNodeExecutionRecord,
    PlanStatus,
)
from app.planner.validator import PlanValidator
from app.schemas.event import ExecutionEventType
from app.tools.service import ToolService

logger = get_logger("aegis.planner.service")


class PlannerService:
    """
    Application boundary for Task Planning and Execution Graph orchestration.
    Enforces multi-tenant ownership boundaries, monotonic event sequencing, and safe execution.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        tool_service: ToolService | None = None,
        memory_service: MemoryService | None = None,
        policy: PlannerPolicy | None = None,
        event_emitter: EventEmitter | None = None,
        repository: PlannerRepository | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:
        self.policy = policy or PlannerPolicy()
        self.event_emitter = event_emitter or EventEmitter()
        self.repository = repository or PlannerRepository()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.tool_service = tool_service or ToolService()
        self.memory_service = memory_service
        self.validator = PlanValidator(policy=self.policy, tool_registry=self.tool_service.registry)

        self.deterministic_planner = DeterministicPlanner()
        self.planner = (
            LLMPlanner(
                llm_provider=llm_provider,
                validator=self.validator,
                deterministic_fallback=self.deterministic_planner,
            )
            if llm_provider
            else self.deterministic_planner
        )

        self.executor = GraphExecutor(
            tool_service=self.tool_service,
            llm_provider=llm_provider,
            policy=self.policy,
            event_emitter=self.event_emitter,
            checkpoint_manager=self.checkpoint_manager,
        )

        # Active in-memory cancellation tokens
        self._cancellation_tokens: dict[uuid.UUID, asyncio.Event] = {}

    async def _verify_task_ownership(
        self,
        task_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> Task:
        """Verify task exists and belongs to the trusted user context."""
        stmt = select(Task).where(Task.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise PlanNotFoundError(f"Task with ID '{task_id}' not found.")

        if task.user_id is not None and task.user_id != trusted_user_id:
            raise PlanNotFoundError(f"Task with ID '{task_id}' not found.")

        return task

    async def create_and_validate_plan(
        self,
        request: PlanCreateRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionPlan:
        """
        Create, decompose, topologically validate, and persist an ExecutionPlan.
        """
        task = await self._verify_task_ownership(request.task_id, trusted_user_id, session)

        await self.event_emitter.emit(
            task_id=task.id,
            run_id=request.run_id,
            event_type=ExecutionEventType.PLAN_CREATED,
            payload={"objective": request.objective},
            session=session,
        )

        # Optional Memory Recall context gathering
        planning_context: dict[str, Any] = dict(request.metadata)
        if self.memory_service:
            try:
                mem_query = MemorySearchQuery(
                    query_text=request.objective,
                    limit=3,
                )
                memories = await self.memory_service.recall(
                    query=mem_query,
                    trusted_user_id=trusted_user_id,
                    session=session,
                )
                if memories:
                    planning_context["recalled_memories"] = [
                        {"content": m.record.content, "score": m.score} for m in memories
                    ]
            except Exception as mem_err:
                logger.warning(f"Optional planner memory recall failed: {mem_err}")

        # Generate or adopt nodes
        if request.nodes:
            plan = ExecutionPlan(
                plan_id=uuid.uuid4(),
                task_id=request.task_id,
                run_id=request.run_id,
                objective=request.objective,
                version=1,
                nodes=request.nodes,
                status=PlanStatus.DRAFT,
                metadata=planning_context,
            )
        else:
            plan = await self.planner.create_plan(
                objective=request.objective,
                task_id=request.task_id,
                run_id=request.run_id,
                context=planning_context,
            )

        # Validate DAG topology and security bounds
        try:
            self.validator.validate_plan(plan)
            plan.status = PlanStatus.VALIDATED

            await self.event_emitter.emit(
                task_id=task.id,
                run_id=request.run_id,
                event_type=ExecutionEventType.PLAN_VALIDATED,
                payload={"plan_id": str(plan.plan_id), "node_count": len(plan.nodes)},
                session=session,
            )
        except Exception as val_err:
            plan.status = PlanStatus.FAILED
            await self.event_emitter.emit(
                task_id=task.id,
                run_id=request.run_id,
                event_type=ExecutionEventType.PLAN_VALIDATION_FAILED,
                payload={"error": str(val_err)},
                session=session,
            )
            raise

        # Persist to database
        await self.repository.create_plan(plan, user_id=trusted_user_id, session=session)
        await session.commit()

        return plan

    async def get_plan(
        self,
        plan_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionPlan:
        """Fetch execution plan by UUID with strict tenant ownership verification."""
        model = await self.repository.get_plan_by_id(plan_id, session)
        if not model:
            raise PlanNotFoundError(f"Execution plan '{plan_id}' not found.")

        if model.user_id is not None and model.user_id != trusted_user_id:
            raise PlanNotFoundError(f"Execution plan '{plan_id}' not found.")

        raw_nodes = model.graph.get("nodes", [])
        nodes = [PlanNode(**n) for n in raw_nodes]

        return ExecutionPlan(
            plan_id=model.id,
            task_id=model.task_id,
            run_id=model.run_id,
            objective=model.objective,
            version=model.version,
            nodes=nodes,
            status=PlanStatus(model.status),
            metadata=model.plan_metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def execute_plan(
        self,
        plan_id: uuid.UUID,
        request: PlanExecuteRequest,
        trusted_user_id: uuid.UUID,
        cancellation_token: asyncio.Event | None = None,
        session: AsyncSession | None = None,
    ) -> PlanExecutionResponse:
        """
        Execute a validated execution plan.
        """
        if session is None:
            raise RuntimeError("Database session required for execute_plan")

        plan = await self.get_plan(plan_id, trusted_user_id, session)

        context = ExecutionContext(
            task_id=plan.task_id,
            run_id=plan.run_id,
            user_id=trusted_user_id,
            plan_id=plan.plan_id,
            variables=dict(request.variables),
        )

        cancel_token = cancellation_token or asyncio.Event()
        self._cancellation_tokens[plan.plan_id] = cancel_token

        await self.repository.update_plan_status(plan.plan_id, PlanStatus.RUNNING, session)
        await session.commit()

        try:
            response = await self.executor.execute_graph(
                plan=plan,
                context=context,
                session=session,
                cancellation_token=cancel_token,
            )

            await self.repository.update_plan_status(plan.plan_id, response.status, session)
            await session.commit()
            return response
        finally:
            self._cancellation_tokens.pop(plan.plan_id, None)

    async def cancel_execution(
        self,
        plan_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionPlan:
        """Signal cancellation for an active execution graph."""
        plan = await self.get_plan(plan_id, trusted_user_id, session)

        cancel_token = self._cancellation_tokens.get(plan_id)
        if cancel_token:
            cancel_token.set()

        await self.repository.update_plan_status(plan_id, PlanStatus.CANCELLED, session)
        await self.event_emitter.emit(
            task_id=plan.task_id,
            run_id=plan.run_id,
            event_type=ExecutionEventType.EXECUTION_CANCELLED,
            payload={"plan_id": str(plan_id)},
            session=session,
        )
        await session.commit()
        plan.status = PlanStatus.CANCELLED
        return plan

    async def resume_plan(
        self,
        plan_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> PlanExecutionResponse:
        """
        Resume an execution plan from its most recent checkpoint snapshot.
        """
        plan = await self.get_plan(plan_id, trusted_user_id, session)
        checkpoint = await self.checkpoint_manager.get_latest_checkpoint(plan_id, session)

        node_statuses: dict[str, NodeStatus] = {}
        node_outputs: dict[str, Any] = {}

        if checkpoint:
            node_statuses = dict(checkpoint.node_states)
            node_outputs = dict(checkpoint.node_outputs)

        context = ExecutionContext(
            task_id=plan.task_id,
            run_id=plan.run_id,
            user_id=trusted_user_id,
            plan_id=plan.plan_id,
            node_statuses=node_statuses,
            node_outputs=node_outputs,
        )

        await self.event_emitter.emit(
            task_id=plan.task_id,
            run_id=plan.run_id,
            event_type=ExecutionEventType.EXECUTION_RESUMED,
            payload={
                "plan_id": str(plan_id),
                "resumed_nodes_completed": len(checkpoint.completed_nodes) if checkpoint else 0,
            },
            session=session,
        )

        cancel_token = asyncio.Event()
        self._cancellation_tokens[plan.plan_id] = cancel_token
        await self.repository.update_plan_status(plan_id, PlanStatus.RUNNING, session)
        await session.commit()

        try:
            response = await self.executor.execute_graph(
                plan=plan,
                context=context,
                session=session,
                cancellation_token=cancel_token,
            )
            await self.repository.update_plan_status(plan.plan_id, response.status, session)
            await session.commit()
            return response
        finally:
            self._cancellation_tokens.pop(plan.plan_id, None)

    async def get_node_executions(
        self,
        plan_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[PlanNodeExecutionRecord]:
        """Fetch all node execution audit traces for a plan."""
        await self.get_plan(plan_id, trusted_user_id, session)
        models = await self.repository.get_node_executions_by_plan_id(plan_id, session)
        return [
            PlanNodeExecutionRecord(
                node_execution_id=m.id,
                plan_id=m.plan_id,
                node_id=m.node_id,
                status=NodeStatus(m.status),
                attempt=m.attempt,
                started_at=m.started_at,
                completed_at=m.completed_at,
                output=m.output,
                error=m.error,
                metadata=m.node_metadata,
            )
            for m in models
        ]
