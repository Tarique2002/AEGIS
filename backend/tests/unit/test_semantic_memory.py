"""Unit tests for Qdrant-backed SemanticMemoryStore and deduplication."""

import uuid

import pytest
from app.memory.schemas import MemoryRecord, MemorySearchQuery, MemoryType
from app.memory.semantic.embeddings import MockEmbeddingProvider
from app.memory.semantic.store import SemanticMemoryStore
from tests.unit.memory_fakes import FakeQdrantClient


@pytest.mark.asyncio
async def test_semantic_memory_store_and_get():
    fake_qdrant = FakeQdrantClient()
    provider = MockEmbeddingProvider(dimension=128)
    store = SemanticMemoryStore(qdrant_client=fake_qdrant, embedding_provider=provider)

    user_id = uuid.uuid4()
    record = MemoryRecord(
        memory_type=MemoryType.SEMANTIC,
        user_id=user_id,
        content="AEGIS uses a multi-layer memory engine architecture.",
        importance=0.9,
    )

    saved = await store.store(record)
    assert saved.memory_id == record.memory_id

    # Retrieve
    retrieved = await store.get(record.memory_id, user_id)
    assert retrieved is not None
    assert retrieved.content == record.content
    assert retrieved.importance == 0.9


@pytest.mark.asyncio
async def test_semantic_memory_two_stage_deduplication():
    fake_qdrant = FakeQdrantClient()
    provider = MockEmbeddingProvider(dimension=128)
    store = SemanticMemoryStore(qdrant_client=fake_qdrant, embedding_provider=provider)

    user_id = uuid.uuid4()
    record1 = MemoryRecord(
        memory_type=MemoryType.SEMANTIC,
        user_id=user_id,
        content="PostgreSQL stores episodic summaries.",
        importance=0.8,
    )
    await store.store(record1)

    # Stage 1: Exact duplicate string detection
    duplicate_exact = await store.find_duplicate("PostgreSQL stores episodic summaries.", user_id)
    assert duplicate_exact is not None
    assert duplicate_exact.memory_id == record1.memory_id

    # Stage 2: Semantic vector match
    duplicate_semantic = await store.find_duplicate(
        "PostgreSQL stores episodic summaries.",
        user_id,
        threshold=0.95,
    )
    assert duplicate_semantic is not None

    # Novel text should NOT be detected as duplicate
    novel = await store.find_duplicate("Completely different topic about astronomy", user_id)
    assert novel is None


@pytest.mark.asyncio
async def test_semantic_memory_user_isolation():
    fake_qdrant = FakeQdrantClient()
    store = SemanticMemoryStore(qdrant_client=fake_qdrant)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    rec_a = MemoryRecord(
        memory_type=MemoryType.SEMANTIC,
        user_id=user_a,
        content="Confidential project details for User A",
    )
    await store.store(rec_a)

    # User A can access
    assert await store.get(rec_a.memory_id, user_a) is not None

    # User B CANNOT access User A's semantic memory
    assert await store.get(rec_a.memory_id, user_b) is None

    # User B search returns 0 results for User A's content
    query_b = MemorySearchQuery(query_text="Confidential project", user_id=user_b)
    results_b = await store.search(query_b)
    assert len(results_b) == 0
