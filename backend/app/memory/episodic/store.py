"""PostgreSQL-backed Episodic Memory Store."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionLocal
from app.memory.base import BaseMemoryStore
from app.memory.episodic.repository import EpisodicMemoryRepository
from app.memory.errors import MemoryStorageError
from app.memory.schemas import (
    EpisodicMemoryRecord,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryType,
)


class EpisodicMemoryStore(BaseMemoryStore):
    """
    Episodic Memory Store backed by PostgreSQL.
    Captures summaries of agent experiences (tasks, runs, outcomes).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        repository: EpisodicMemoryRepository | None = None,
    ) -> None:
        self.session_factory = session_factory or AsyncSessionLocal

        self.repository = repository or EpisodicMemoryRepository()

    @property
    def memory_type(self) -> MemoryType:
        return MemoryType.EPISODIC

    async def record_episode(
        self,
        episode: EpisodicMemoryRecord,
        session: AsyncSession | None = None,
    ) -> EpisodicMemoryRecord:
        """Store an episodic memory record."""
        if session:
            model = await self.repository.create_episode(session, episode)
            return self._model_to_record(model)

        async with self.session_factory() as s, s.begin():
            model = await self.repository.create_episode(s, episode)
            return self._model_to_record(model)

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        """Adapter storing MemoryRecord as an episodic record."""
        episode = EpisodicMemoryRecord(
            episode_id=record.memory_id,
            user_id=record.user_id,
            task_id=record.task_id or uuid.UUID(int=0),
            run_id=record.run_id or uuid.UUID(int=0),
            objective=record.metadata.get("objective", "Task objective"),
            summary=record.content,
            actions=record.metadata.get("actions", []),
            observations=record.metadata.get("observations", []),
            result=record.metadata.get("result"),
            status=record.metadata.get("status", "completed"),
            importance=record.importance,
            metadata=record.metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        saved = await self.record_episode(episode)
        return self._episode_to_memory_record(saved)

    async def get(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MemoryRecord | None:
        """Retrieve episodic memory record by ID with user isolation."""
        try:
            async with self.session_factory() as session:
                model = await self.repository.get_by_id(session, memory_id, user_id)
                if not model:
                    return None
                return self._episode_to_memory_record(self._model_to_record(model))
        except Exception as exc:
            raise MemoryStorageError(f"Failed to retrieve episodic memory: {exc}") from exc

    async def delete(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete episodic memory record by ID with user isolation."""
        try:
            async with self.session_factory() as session, session.begin():
                return await self.repository.delete_by_id(session, memory_id, user_id)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to delete episodic memory: {exc}") from exc

    async def search(
        self,
        query: MemorySearchQuery,
    ) -> list[MemorySearchResult]:
        """Search episodic memories matching query text for the trusted user."""
        user_id = query.user_id
        if not user_id:
            return []

        try:
            async with self.session_factory() as session:
                models = await self.repository.search_by_text(
                    session=session,
                    user_id=user_id,
                    query=query.query_text,
                    limit=query.limit,
                )
                results: list[MemorySearchResult] = []
                for m in models:
                    rec = self._episode_to_memory_record(self._model_to_record(m))
                    results.append(
                        MemorySearchResult(
                            record=rec,
                            score=rec.importance,
                            matched_by="episodic_text_match",
                            similarity_score=0.8,
                            recency_score=1.0,
                            importance_score=rec.importance,
                        )
                    )
                return results
        except Exception as exc:
            raise MemoryStorageError(f"Failed to search episodic memory: {exc}") from exc

    def _model_to_record(self, model) -> EpisodicMemoryRecord:
        return EpisodicMemoryRecord(
            episode_id=model.id,
            user_id=model.user_id,
            task_id=model.task_id,
            run_id=model.run_id,
            objective=model.objective,
            summary=model.summary,
            actions=model.actions,
            observations=model.observations,
            result=model.result,
            status=model.status,
            importance=model.importance,
            metadata=model.memory_metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _episode_to_memory_record(self, episode: EpisodicMemoryRecord) -> MemoryRecord:
        return MemoryRecord(
            memory_id=episode.episode_id,
            memory_type=MemoryType.EPISODIC,
            user_id=episode.user_id,
            task_id=episode.task_id,
            run_id=episode.run_id,
            content=episode.summary,
            importance=episode.importance,
            metadata={
                "objective": episode.objective,
                "actions": episode.actions,
                "observations": episode.observations,
                "result": episode.result,
                "status": episode.status,
                **episode.metadata,
            },
            created_at=episode.created_at,
            updated_at=episode.updated_at,
        )
