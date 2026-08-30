"""SQLAlchemy repository for Phase 7 Orchestration persistence and query-level tenant isolation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.orchestration import (
    DelegatedTaskModel,
    OrchestrationModel,
    WorkerExecutionModel,
)
from app.orchestration.schemas import (
    OrchestrationState,
)


class OrchestrationRepository:
    """Repository managing CRUD operations for Orchestrations and Delegated Tasks."""

    async def create_orchestration(
        self,
        state: OrchestrationState,
        idempotency_key: str | None,
        session: AsyncSession,
    ) -> OrchestrationModel:
        """Create new orchestration database record and related delegated tasks."""
        model = OrchestrationModel(
            id=state.orchestration_id,
            task_id=state.task_id,
            run_id=state.run_id,
            user_id=state.user_id,
            objective=state.objective,
            status=state.status.value,
            delegation_plan_id=state.delegation_plan.plan_id if state.delegation_plan else None,
            idempotency_key=idempotency_key,
            budget=state.budget.model_dump(mode="json"),
            final_result=(
                state.aggregated_result.model_dump(mode="json") if state.aggregated_result else None
            ),
            error=state.errors[0] if state.errors else None,
            orchestration_metadata=state.metadata,
            started_at=state.started_at,
            completed_at=state.completed_at,
        )
        session.add(model)

        if state.delegation_plan:
            for task in state.delegation_plan.tasks:
                task_model = DelegatedTaskModel(
                    id=uuid.uuid4(),
                    orchestration_id=state.orchestration_id,
                    worker_type=task.worker_type.value,
                    title=task.title,
                    objective=task.objective,
                    status=task.status.value,
                    dependencies=task.dependencies,
                    result=None,
                    budget={},
                    task_metadata={"delegated_task_id": task.delegated_task_id},
                )
                session.add(task_model)

        await session.flush()
        return model

    async def get_orchestration(
        self,
        orchestration_id: uuid.UUID,
        session: AsyncSession,
        user_id: uuid.UUID | None = None,
    ) -> OrchestrationModel | None:
        """Fetch orchestration session by ID with optional tenant isolation."""
        stmt = (
            select(OrchestrationModel)
            .where(OrchestrationModel.id == orchestration_id)
            .options(
                selectinload(OrchestrationModel.delegated_tasks),
                selectinload(OrchestrationModel.worker_executions),
            )
        )
        if user_id is not None:
            stmt = stmt.where(OrchestrationModel.user_id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
        user_id: uuid.UUID,
        session: AsyncSession,
    ) -> OrchestrationModel | None:
        """Fetch existing orchestration matching an idempotency key for the authenticated user."""
        stmt = (
            select(OrchestrationModel)
            .where(
                OrchestrationModel.idempotency_key == idempotency_key,
                OrchestrationModel.user_id == user_id,
            )
            .options(
                selectinload(OrchestrationModel.delegated_tasks),
                selectinload(OrchestrationModel.worker_executions),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_orchestration_state(
        self,
        state: OrchestrationState,
        session: AsyncSession,
    ) -> None:
        """Persist state updates, completed results, and worker executions."""
        model = await self.get_orchestration(state.orchestration_id, session)
        if not model:
            return

        model.status = state.status.value
        model.budget = state.budget.model_dump(mode="json")
        model.final_result = (
            state.aggregated_result.model_dump(mode="json") if state.aggregated_result else None
        )
        model.error = state.errors[0] if state.errors else None
        model.completed_at = state.completed_at

        # Save worker execution records
        for _task_id, res in state.worker_results.items():
            exec_model = WorkerExecutionModel(
                id=uuid.uuid4(),
                orchestration_id=state.orchestration_id,
                delegated_task_id=uuid.uuid4(),  # synthetic FK if standalone
                worker_id=res.worker_id,
                status=res.status.value,
                result={"data": res.result} if res.result is not None else None,
                evaluation=res.evaluation.model_dump(mode="json") if res.evaluation else None,
                started_at=res.started_at,
                completed_at=res.completed_at,
                duration_ms=res.duration_ms,
                error=res.error,
                execution_metadata=res.metadata,
            )
            session.add(exec_model)

        await session.flush()
