"""Task Service boundary decoupling API routing from AgentRuntime execution."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.runtime import AgentRuntime
from app.core.errors import AegisNotFoundError
from app.db.models.event import ExecutionEventModel
from app.db.models.task import Task
from app.llm.base import LLMProvider
from app.schemas.common import StepStatus, TaskStatus
from app.schemas.event import ExecutionEvent, ExecutionEventType
from app.schemas.task import (
    AgentRunRead,
    TaskCreate,
    TaskExecutionResponse,
    TaskRead,
    TaskStepRead,
)


class TaskService:
    """
    Service layer providing isolation between HTTP endpoints and AgentRuntime.
    Facilitates future migration to background worker queues without API breakage.
    """

    def __init__(self, runtime: AgentRuntime | None = None) -> None:
        self.runtime = runtime or AgentRuntime()

    async def create_and_execute_task(
        self,
        task_in: TaskCreate,
        session: AsyncSession,
        provider: LLMProvider | None = None,
    ) -> TaskExecutionResponse:
        """
        Create a new task and execute a foundational runtime pass synchronously.
        """
        runtime = AgentRuntime(provider=provider) if provider else self.runtime
        state = await runtime.execute_task(
            objective=task_in.objective,
            session=session,
            user_id=task_in.user_id,
            metadata=task_in.metadata,
        )

        assert state.run_id is not None

        return TaskExecutionResponse(
            task_id=state.task_id,
            run_id=state.run_id,
            status=state.status,
            objective=state.objective,
            result=state.final_result,
            telemetry=state.telemetry,
            created_at=state.created_at,
            completed_at=state.completed_at,
        )

    async def get_task_by_id(
        self,
        task_id: uuid.UUID,
        session: AsyncSession,
    ) -> TaskRead:
        """
        Retrieve a task along with its execution runs and plan steps.
        """
        stmt = (
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.runs),
                selectinload(Task.steps),
            )
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise AegisNotFoundError(f"Task with ID '{task_id}' not found.")

        runs_read = [
            AgentRunRead(
                id=run.id,
                task_id=run.task_id,
                run_type=run.run_type,
                model_used=run.model_used,
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                total_tokens=run.total_tokens,
                estimated_cost_usd=run.estimated_cost_usd,
                latency_ms=run.latency_ms,
                status=run.status,
                result=run.result,
                error=run.error,
                started_at=run.started_at,
                ended_at=run.ended_at,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            for run in task.runs
        ]

        steps_read = [
            TaskStepRead(
                id=step.id,
                task_id=step.task_id,
                step_order=step.step_order,
                title=step.title,
                description=step.description,
                status=StepStatus(step.status),
                required_tools=step.required_tools,
                dependencies=step.dependencies,
                expected_output=step.expected_output,
                result=step.result,
                error=step.error,
                started_at=step.started_at,
                completed_at=step.completed_at,
                created_at=step.created_at,
                updated_at=step.updated_at,
            )
            for step in task.steps
        ]

        return TaskRead(
            id=task.id,
            user_id=task.user_id,
            objective=task.objective,
            status=TaskStatus(task.status),
            result=task.result,
            task_metadata=task.task_metadata,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            steps=steps_read,
            runs=runs_read,
        )

    async def get_task_events(
        self,
        task_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[ExecutionEvent]:
        """
        Retrieve all execution events for a task in deterministic sequence and chronological order.
        """
        # Ensure task exists
        task_stmt = select(Task.id).where(Task.id == task_id)
        task_res = await session.execute(task_stmt)
        if not task_res.scalar_one_or_none():
            raise AegisNotFoundError(f"Task with ID '{task_id}' not found.")

        stmt = (
            select(ExecutionEventModel)
            .where(ExecutionEventModel.task_id == task_id)
            .order_by(
                ExecutionEventModel.sequence_number.asc(),
                ExecutionEventModel.timestamp.asc(),
            )
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        return [
            ExecutionEvent(
                event_id=ev.id,
                task_id=ev.task_id,
                run_id=ev.run_id,
                event_type=ExecutionEventType(ev.event_type),
                timestamp=ev.timestamp,
                sequence_number=ev.sequence_number,
                payload=ev.payload,
            )
            for ev in events
        ]
