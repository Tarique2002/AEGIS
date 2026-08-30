"""SQLAlchemy repository for persisting Agent Loops, Iteration records, and Checkpoints."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent_loop.schemas import AgentLoopState, AutonomyLevel
from app.db.models.loop import AgentIterationModel, AgentLoopModel


class AgentLoopRepository:
    """Async database repository for agent loop states and audit iteration records."""

    async def create_loop(
        self,
        loop_state: AgentLoopState,
        autonomy_level: AutonomyLevel = AutonomyLevel.BOUNDED,
        idempotency_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> AgentLoopModel:
        """Persist a newly initialized agent loop."""
        if session is None:
            raise RuntimeError("Database session required for create_loop")

        model = AgentLoopModel(
            id=loop_state.loop_id,
            task_id=loop_state.task_id,
            run_id=loop_state.run_id,
            user_id=loop_state.user_id,
            objective=loop_state.objective,
            status=loop_state.status.value,
            iteration_number=loop_state.iteration_number,
            autonomy_level=autonomy_level.value,
            idempotency_key=idempotency_key,
            budget=loop_state.budget.model_dump(),
            final_result={"result": loop_state.final_result}
            if loop_state.final_result is not None
            else None,
            loop_metadata=loop_state.metadata,
            started_at=loop_state.started_at,
            completed_at=loop_state.completed_at,
        )
        session.add(model)
        await session.flush()
        return model

    async def get_loop(
        self,
        loop_id: uuid.UUID,
        session: AsyncSession,
        user_id: uuid.UUID | None = None,
    ) -> AgentLoopModel | None:
        """Fetch an agent loop with eager-loaded iteration records and ownership filtering."""
        stmt = (
            select(AgentLoopModel)
            .where(AgentLoopModel.id == loop_id)
            .options(selectinload(AgentLoopModel.iterations))
        )
        if user_id is not None:
            stmt = stmt.where(AgentLoopModel.user_id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
        user_id: uuid.UUID,
        session: AsyncSession,
    ) -> AgentLoopModel | None:
        """Fetch existing loop matching an idempotency key for the authenticated user."""
        stmt = (
            select(AgentLoopModel)
            .where(
                AgentLoopModel.idempotency_key == idempotency_key,
                AgentLoopModel.user_id == user_id,
            )
            .options(selectinload(AgentLoopModel.iterations))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_loop_state(
        self,
        loop_state: AgentLoopState,
        session: AsyncSession,
    ) -> None:
        """Update loop state and persist newly completed iteration records."""
        model = await self.get_loop(loop_state.loop_id, session)
        if not model:
            return

        model.status = loop_state.status.value
        model.iteration_number = loop_state.iteration_number
        model.budget = loop_state.budget.model_dump()
        model.final_result = (
            {"result": loop_state.final_result} if loop_state.final_result is not None else None
        )
        model.completed_at = loop_state.completed_at
        model.loop_metadata = loop_state.metadata

        # Persist iterations
        existing_iter_nums = {it.iteration_number for it in model.iterations}
        for iter_rec in loop_state.completed_iterations:
            if iter_rec.iteration_number not in existing_iter_nums:
                iter_model = AgentIterationModel(
                    id=iter_rec.iteration_id,
                    loop_id=iter_rec.loop_id,
                    iteration_number=iter_rec.iteration_number,
                    status=iter_rec.status.value,
                    observation=iter_rec.observation.model_dump(mode="json")
                    if iter_rec.observation
                    else None,
                    decision=iter_rec.decision.model_dump(mode="json")
                    if iter_rec.decision
                    else None,
                    plan_id=iter_rec.plan_id,
                    evaluation_id=iter_rec.evaluation_id,
                    reflection_id=iter_rec.reflection_id,
                    started_at=iter_rec.started_at,
                    completed_at=iter_rec.completed_at,
                    error=iter_rec.error,
                    iteration_metadata=iter_rec.metadata,
                )
                session.add(iter_model)

        await session.flush()

    async def get_iterations(
        self,
        loop_id: uuid.UUID,
        session: AsyncSession,
        user_id: uuid.UUID | None = None,
    ) -> list[AgentIterationModel]:
        """Fetch all iterations ordered by iteration number, verifying loop ownership."""
        if user_id is not None:
            loop = await self.get_loop(loop_id, session, user_id=user_id)
            if not loop:
                return []
        stmt = (
            select(AgentIterationModel)
            .where(AgentIterationModel.loop_id == loop_id)
            .order_by(AgentIterationModel.iteration_number.asc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
