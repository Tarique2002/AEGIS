"""Unit tests for MemoryManager layer routing, recall, and lifecycle."""

import uuid

import pytest
from app.memory.manager import MemoryManager
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.schemas import MemoryCandidate, MemorySearchQuery, MemoryType
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.working.store import WorkingMemoryStore
from tests.unit.memory_fakes import FakeQdrantClient, FakeRedisClient


@pytest.mark.asyncio
async def test_memory_manager_remember_and_recall():
    fake_redis = FakeRedisClient()
    fake_qdrant = FakeQdrantClient()

    working_store = WorkingMemoryStore(redis_client=fake_redis)
    semantic_store = SemanticMemoryStore(qdrant_client=fake_qdrant)
    procedural_store = ProceduralMemoryStore()

    manager = MemoryManager(
        working_store=working_store,
        semantic_store=semantic_store,
        procedural_store=procedural_store,
    )

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    # 1. Ingest Semantic Memory
    cand_sem = MemoryCandidate(
        content="Python 3.12 introduces improved performance and type parameter syntax.",
        memory_type=MemoryType.SEMANTIC,
        importance=0.8,
    )
    rec_sem = await manager.remember(cand_sem, user_id=user_id)
    assert rec_sem.memory_id is not None

    # 2. Ingest Working Memory
    cand_work = MemoryCandidate(
        content="Temporary scratchpad calculation state",
        memory_type=MemoryType.WORKING,
        task_id=task_id,
    )
    rec_work = await manager.remember(cand_work, user_id=user_id)
    assert rec_work.memory_id is not None

    # 3. Recall
    query = MemorySearchQuery(query_text="performance", memory_types=[MemoryType.SEMANTIC])
    results = await manager.recall(query, user_id=user_id)
    assert len(results) >= 1
    assert "Python 3.12" in results[0].record.content


@pytest.mark.asyncio
async def test_memory_manager_deduplication():
    fake_qdrant = FakeQdrantClient()
    semantic_store = SemanticMemoryStore(qdrant_client=fake_qdrant)
    manager = MemoryManager(semantic_store=semantic_store)

    user_id = uuid.uuid4()
    cand = MemoryCandidate(
        content="Identical architectural decision memory.",
        memory_type=MemoryType.SEMANTIC,
    )

    # First write
    rec1 = await manager.remember(cand, user_id=user_id)

    # Second write of exact same candidate
    rec2 = await manager.remember(cand, user_id=user_id)

    # Must return the existing record instead of creating duplicate
    assert rec1.memory_id == rec2.memory_id


@pytest.mark.asyncio
async def test_memory_manager_forget():
    fake_qdrant = FakeQdrantClient()
    semantic_store = SemanticMemoryStore(qdrant_client=fake_qdrant)
    manager = MemoryManager(semantic_store=semantic_store)

    user_id = uuid.uuid4()
    cand = MemoryCandidate(content="Memory to be forgotten", memory_type=MemoryType.SEMANTIC)
    rec = await manager.remember(cand, user_id=user_id)

    # Verify present
    assert await manager.get_by_id(rec.memory_id, user_id) is not None

    # Forget
    deleted = await manager.forget(rec.memory_id, user_id)
    assert deleted is True
