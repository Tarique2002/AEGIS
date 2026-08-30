"""Data access repository for Execution Plans, Nodes, and Checkpoints."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.plan import (
    ExecutionNodeModel,
    ExecutionPlanModel,
)
from app.planner.schemas import ExecutionPlan, PlanNodeExecutionRecord, PlanStatus


class PlannerRepository:
    """Async repository managing database persistence for execution plans and node traces."""

    async def create_plan(
        self,
        plan: ExecutionPlan,
        user_id: uuid.UUID | None,
        session: AsyncSession,
    ) -> ExecutionPlanModel:
        """Persist a new execution plan record."""
        model = ExecutionPlanModel(
            id=plan.plan_id,
            task_id=plan.task_id,
            run_id=plan.run_id,
            user_id=user_id,
            objective=plan.objective,
            version=plan.version,
            status=plan.status.value,
            graph={"nodes": [n.model_dump(mode="json") for n in plan.nodes]},
            plan_metadata=plan.metadata,
        )
        session.add(model)
        await session.flush()
        return model

    async def get_plan_by_id(
        self,
        plan_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionPlanModel | None:
        """Fetch execution plan by primary key UUID."""
        stmt = select(ExecutionPlanModel).where(ExecutionPlanModel.id == plan_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_plan_status(
        self,
        plan_id: uuid.UUID,
        status: PlanStatus,
        session: AsyncSession,
    ) -> None:
        """Update lifecycle status of an execution plan."""
        stmt = (
            update(ExecutionPlanModel)
            .where(ExecutionPlanModel.id == plan_id)
            .values(status=status.value)
        )
        await session.execute(stmt)
        await session.flush()

    async def record_node_execution(
        self,
        record: PlanNodeExecutionRecord,
        session: AsyncSession,
    ) -> ExecutionNodeModel:
        """Record an individual node execution trace."""
        model = ExecutionNodeModel(
            id=record.node_execution_id,
            plan_id=record.plan_id,
            node_id=record.node_id,
            status=record.status.value,
            attempt=record.attempt,
            started_at=record.started_at,
            completed_at=record.completed_at,
            output=record.output,
            error=record.error,
            node_metadata=record.metadata,
        )
        session.add(model)
        await session.flush()
        return model

    async def get_node_executions_by_plan_id(
        self,
        plan_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[ExecutionNodeModel]:
        """Fetch all node execution audit traces for a plan."""
        stmt = (
            select(ExecutionNodeModel)
            .where(ExecutionNodeModel.plan_id == plan_id)
            .order_by(ExecutionNodeModel.created_at.asc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
