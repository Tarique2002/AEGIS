"""Database repository for EpisodicMemory operations."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.episode import EpisodicMemoryModel
from app.memory.schemas import EpisodicMemoryRecord


class EpisodicMemoryRepository:
    """Async database repository for EpisodicMemoryModel entities."""

    async def create_episode(
        self,
        session: AsyncSession,
        episode: EpisodicMemoryRecord,
    ) -> EpisodicMemoryModel:
        """Create and persist an episodic memory record."""
        model = EpisodicMemoryModel(
            id=episode.episode_id,
            user_id=episode.user_id,
            task_id=episode.task_id,
            run_id=episode.run_id,
            objective=episode.objective,
            summary=episode.summary,
            actions=episode.actions,
            observations=episode.observations,
            result=episode.result,
            status=episode.status,
            importance=episode.importance,
            memory_metadata=episode.metadata,
            created_at=episode.created_at,
            updated_at=episode.updated_at,
        )
        session.add(model)
        await session.flush()
        await session.refresh(model)
        return model

    async def get_by_id(
        self,
        session: AsyncSession,
        episode_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> EpisodicMemoryModel | None:
        """Retrieve an episode by ID with mandatory user isolation."""
        stmt = select(EpisodicMemoryModel).where(
            EpisodicMemoryModel.id == episode_id,
            EpisodicMemoryModel.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[EpisodicMemoryModel]:
        """List episodic memories belonging to a specific user."""
        stmt = (
            select(EpisodicMemoryModel)
            .where(EpisodicMemoryModel.user_id == user_id)
            .order_by(EpisodicMemoryModel.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_id(
        self,
        session: AsyncSession,
        episode_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete an episode by ID with user isolation."""
        stmt = delete(EpisodicMemoryModel).where(
            EpisodicMemoryModel.id == episode_id,
            EpisodicMemoryModel.user_id == user_id,
        )
        result = await session.execute(stmt)
        rowcount = int(getattr(result, "rowcount", 0))
        return bool(rowcount > 0)

    async def search_by_text(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        query: str,
        limit: int = 5,
    ) -> list[EpisodicMemoryModel]:
        """Search episodes by matching text against summary and objective."""
        pattern = f"%{query.strip()}%"
        stmt = (
            select(EpisodicMemoryModel)
            .where(
                EpisodicMemoryModel.user_id == user_id,
                (EpisodicMemoryModel.summary.ilike(pattern))
                | (EpisodicMemoryModel.objective.ilike(pattern)),
            )
            .order_by(EpisodicMemoryModel.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
