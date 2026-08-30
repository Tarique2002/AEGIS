"""Unit tests for multi-tier memory retrieval and weighted scoring."""

import uuid

import pytest
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.manager import MemoryManager
from app.memory.policies import MemoryPolicy
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.schemas import MemoryCandidate, MemorySearchQuery, MemoryType
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.working.store import WorkingMemoryStore
from tests.conftest import TestAsyncSessionLocal
from tests.unit.memory_fakes import FakeQdrantClient, FakeRedisClient


@pytest.mark.asyncio
async def test_multi_tier_retrieval_ranking():
    fake_qdrant = FakeQdrantClient()
    fake_redis = FakeRedisClient()
    policy = MemoryPolicy(weight_similarity=0.6, weight_recency=0.2, weight_importance=0.2)

    semantic_store = SemanticMemoryStore(qdrant_client=fake_qdrant, policy=policy)
    procedural_store = ProceduralMemoryStore()
    episodic_store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)
    working_store = WorkingMemoryStore(redis_client=fake_redis)

    manager = MemoryManager(
        semantic_store=semantic_store,
        procedural_store=procedural_store,
        episodic_store=episodic_store,
        working_store=working_store,
        policy=policy,
    )

    user_id = uuid.uuid4()

    # Ingest High Importance semantic memory
    await manager.remember(
        MemoryCandidate(
            content="Critical security guideline: never expose raw SQL to user input.",
            memory_type=MemoryType.SEMANTIC,
            importance=1.0,
        ),
        user_id=user_id,
    )

    # Ingest Low Importance semantic memory
    await manager.remember(
        MemoryCandidate(
            content="Minor note: SQL comments start with --.",
            memory_type=MemoryType.SEMANTIC,
            importance=0.2,
        ),
        user_id=user_id,
    )

    # Recall
    query = MemorySearchQuery(query_text="SQL security guideline", limit=5)
    results = await manager.recall(query, user_id=user_id)

    assert len(results) >= 2
    # The high importance security guideline should be ranked higher
    assert results[0].score >= results[1].score
    assert "Critical security guideline" in results[0].record.content


@pytest.mark.asyncio
async def test_retrieval_limit_capping():
    fake_qdrant = FakeQdrantClient()
    fake_redis = FakeRedisClient()
    policy = MemoryPolicy(max_retrieval_limit=3)
    episodic_store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)
    working_store = WorkingMemoryStore(redis_client=fake_redis)
    manager = MemoryManager(
        semantic_store=SemanticMemoryStore(qdrant_client=fake_qdrant, policy=policy),
        episodic_store=episodic_store,
        working_store=working_store,
        policy=policy,
    )

    user_id = uuid.uuid4()
    for i in range(10):
        await manager.remember(
            MemoryCandidate(content=f"Indexed note number {i} on system setup."),
            user_id=user_id,
        )

    # Request 10 results -> must be capped to max_retrieval_limit (3)
    query = MemorySearchQuery(query_text="system setup", limit=10)
    results = await manager.recall(query, user_id=user_id)
    assert len(results) <= 3
