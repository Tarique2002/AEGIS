"""Unified Memory Manager coordinating Working, Episodic, Semantic, and Procedural memory stores."""

import uuid

from app.memory.base import BaseMemoryStore
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.errors import MemoryNotFoundError, MemoryValidationError
from app.memory.policies import MemoryPolicy
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.schemas import (
    MemoryCandidate,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryStatus,
    MemoryType,
)
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.working.store import WorkingMemoryStore
from app.schemas.common import utc_now


class MemoryManager:
    """
    Central memory orchestrator for AEGIS.
    Routes ingestion and retrieval across memory tiers, enforces deduplication and ranking.
    """

    def __init__(
        self,
        working_store: WorkingMemoryStore | None = None,
        episodic_store: EpisodicMemoryStore | None = None,
        semantic_store: SemanticMemoryStore | None = None,
        procedural_store: ProceduralMemoryStore | None = None,
        policy: MemoryPolicy | None = None,
    ) -> None:
        self.working_store = working_store or WorkingMemoryStore()
        self.episodic_store = episodic_store or EpisodicMemoryStore()
        self.semantic_store = semantic_store or SemanticMemoryStore()
        self.procedural_store = procedural_store or ProceduralMemoryStore()
        self.policy = policy or MemoryPolicy()

    async def remember(
        self,
        candidate: MemoryCandidate,
        user_id: uuid.UUID,
    ) -> MemoryRecord:
        """
        Ingest a proposed memory candidate through validation, policy checks,
        deduplication, and routing to the target memory tier.
        """
        # 1. Validation & Policy
        self.policy.validate_candidate(candidate)

        # 2. Semantic Deduplication (Stage 1 Exact Hash & Stage 2 Vector Similarity)
        if candidate.memory_type == MemoryType.SEMANTIC:
            existing_duplicate = await self.semantic_store.find_duplicate(
                content=candidate.content,
                user_id=user_id,
                threshold=self.policy.semantic_dedup_threshold,
            )
            if existing_duplicate is not None:
                return existing_duplicate

        # 3. Create Record
        now = utc_now()
        record = MemoryRecord(
            memory_id=uuid.uuid4(),
            memory_type=candidate.memory_type,
            user_id=user_id,
            task_id=candidate.task_id,
            run_id=candidate.run_id,
            content=candidate.content,
            importance=candidate.importance,
            status=MemoryStatus.ACTIVE,
            metadata=candidate.metadata,
            created_at=now,
            updated_at=now,
        )

        # 4. Route to target store
        if candidate.memory_type == MemoryType.WORKING:
            return await self.working_store.store(record)
        elif candidate.memory_type == MemoryType.EPISODIC:
            return await self.episodic_store.store(record)
        elif candidate.memory_type == MemoryType.SEMANTIC:
            return await self.semantic_store.store(record)
        elif candidate.memory_type == MemoryType.PROCEDURAL:
            return await self.procedural_store.store(record)
        else:
            raise MemoryValidationError(f"Unsupported memory type: {candidate.memory_type}")

    async def recall(
        self,
        query: MemorySearchQuery,
        user_id: uuid.UUID,
    ) -> list[MemorySearchResult]:
        """
        Retrieve and rank relevant memories across selected tiers with mandatory user isolation.
        """
        # Enforce trusted user_id and retrieval bounds
        query.user_id = user_id
        effective_limit = min(query.limit, self.policy.max_retrieval_limit)
        query.limit = effective_limit

        target_types = query.memory_types or [
            MemoryType.SEMANTIC,
            MemoryType.EPISODIC,
            MemoryType.PROCEDURAL,
            MemoryType.WORKING,
        ]

        all_results: list[MemorySearchResult] = []

        if MemoryType.SEMANTIC in target_types:
            sem_results = await self.semantic_store.search(query)
            all_results.extend(sem_results)

        if MemoryType.EPISODIC in target_types:
            epi_results = await self.episodic_store.search(query)
            all_results.extend(epi_results)

        if MemoryType.PROCEDURAL in target_types:
            proc_results = await self.procedural_store.search(query)
            all_results.extend(proc_results)

        if MemoryType.WORKING in target_types:
            work_results = await self.working_store.search(query)
            all_results.extend(work_results)

        # Filter by minimum score and sort by multi-factor score
        filtered = [r for r in all_results if r.score >= query.min_score]
        filtered.sort(key=lambda r: r.score, reverse=True)
        return filtered[:effective_limit]

    async def get_by_id(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        memory_type: MemoryType | None = None,
    ) -> MemoryRecord:
        """Retrieve memory by ID across stores with user isolation."""
        stores: list[BaseMemoryStore] = (
            [self._get_store_for_type(memory_type)]
            if memory_type
            else [
                self.semantic_store,
                self.episodic_store,
                self.procedural_store,
                self.working_store,
            ]
        )

        for store in stores:
            try:
                rec = await store.get(memory_id, user_id)
                if rec is not None:
                    return rec
            except Exception:
                continue

        raise MemoryNotFoundError(
            f"Memory record '{memory_id}' not found for current user.",
            details={"memory_id": str(memory_id)},
        )

    async def forget(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        memory_type: MemoryType | None = None,
    ) -> bool:
        """Delete memory item across stores with user isolation."""
        stores: list[BaseMemoryStore] = (
            [self._get_store_for_type(memory_type)]
            if memory_type
            else [
                self.semantic_store,
                self.episodic_store,
                self.procedural_store,
                self.working_store,
            ]
        )

        deleted = False

        for store in stores:
            try:
                if await store.delete(memory_id, user_id):
                    deleted = True
            except Exception:
                continue

        if not deleted:
            raise MemoryNotFoundError(
                f"Memory record '{memory_id}' not found to delete.",
                details={"memory_id": str(memory_id)},
            )
        return True

    async def clear_task_memory(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> int:
        """Clear task-specific working memory."""
        return await self.working_store.clear_task_memory(user_id, task_id)

    def _get_store_for_type(self, memory_type: MemoryType) -> BaseMemoryStore:
        if memory_type == MemoryType.WORKING:
            return self.working_store
        elif memory_type == MemoryType.EPISODIC:
            return self.episodic_store
        elif memory_type == MemoryType.SEMANTIC:
            return self.semantic_store
        elif memory_type == MemoryType.PROCEDURAL:
            return self.procedural_store
        raise MemoryValidationError(f"Invalid memory type: {memory_type}")
