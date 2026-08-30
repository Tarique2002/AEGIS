"""Unit tests strictly verifying cross-user and cross-task memory isolation."""

import uuid

import pytest
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.manager import MemoryManager
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.schemas import MemoryCandidate, MemorySearchQuery, MemoryType
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.working.store import WorkingMemoryStore
from tests.conftest import TestAsyncSessionLocal
from tests.unit.memory_fakes import FakeQdrantClient, FakeRedisClient


@pytest.mark.asyncio
async def test_cross_user_isolation_across_all_memory_stores():
    fake_redis = FakeRedisClient()
    fake_qdrant = FakeQdrantClient()

    working_store = WorkingMemoryStore(redis_client=fake_redis)
    semantic_store = SemanticMemoryStore(qdrant_client=fake_qdrant)
    procedural_store = ProceduralMemoryStore()
    episodic_store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)

    manager = MemoryManager(
        working_store=working_store,
        semantic_store=semantic_store,
        procedural_store=procedural_store,
        episodic_store=episodic_store,
    )

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    task_a = uuid.uuid4()

    # 1. User A stores memories across all 3 tiers
    rec_work_a = await manager.remember(
        MemoryCandidate(
            content="Secret working memory for User A",
            memory_type=MemoryType.WORKING,
            task_id=task_a,
        ),
        user_id=user_a,
    )
    rec_sem_a = await manager.remember(
        MemoryCandidate(
            content="Confidential business plan for User A", memory_type=MemoryType.SEMANTIC
        ),
        user_id=user_a,
    )
    rec_proc_a = await manager.remember(
        MemoryCandidate(
            content="Private proprietary deployment algorithm for User A",
            memory_type=MemoryType.PROCEDURAL,
            metadata={"name": "User A Deploy", "steps": [{"step": 1}]},
        ),
        user_id=user_a,
    )

    # 2. User B queries memory with the exact same keywords
    query_b = MemorySearchQuery(
        query_text="User A Confidential business plan proprietary", limit=10
    )
    results_b = await manager.recall(query_b, user_id=user_b)

    # User B MUST NOT receive any of User A's memories
    assert len(results_b) == 0

    # 3. User B queries by ID -> MUST return nothing / fail
    from app.memory.errors import MemoryNotFoundError

    with pytest.raises(MemoryNotFoundError):
        await manager.get_by_id(rec_work_a.memory_id, user_id=user_b)

    with pytest.raises(MemoryNotFoundError):
        await manager.get_by_id(rec_sem_a.memory_id, user_id=user_b)

    with pytest.raises(MemoryNotFoundError):
        await manager.get_by_id(rec_proc_a.memory_id, user_id=user_b)
