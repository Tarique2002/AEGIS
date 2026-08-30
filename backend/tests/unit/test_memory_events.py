"""Unit tests for memory execution events and monotonic sequence ordering."""

import uuid

import pytest
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.manager import MemoryManager
from app.memory.schemas import MemoryCandidate, MemorySearchQuery, MemoryType
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.service import MemoryService
from app.memory.working.store import WorkingMemoryStore
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType
from tests.conftest import TestAsyncSessionLocal
from tests.unit.memory_fakes import FakeQdrantClient, FakeRedisClient


@pytest.mark.asyncio
async def test_memory_events_monotonic_sequence():
    emitter = EventEmitter()
    fake_qdrant = FakeQdrantClient()
    fake_redis = FakeRedisClient()
    episodic_store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)
    working_store = WorkingMemoryStore(redis_client=fake_redis)
    manager = MemoryManager(
        semantic_store=SemanticMemoryStore(qdrant_client=fake_qdrant),
        episodic_store=episodic_store,
        working_store=working_store,
    )
    service = MemoryService(manager=manager, emitter=emitter)

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Pre-emit initial lifecycle event
    await emitter.emit(task_id, run_id, ExecutionEventType.RUN_STARTED, {})

    # Memory write
    rec = await service.remember(
        candidate=MemoryCandidate(
            content="Traceable event memory", memory_type=MemoryType.SEMANTIC
        ),
        trusted_user_id=user_id,
        task_id=task_id,
        run_id=run_id,
    )

    # Memory recall
    await service.recall(
        query=MemorySearchQuery(query_text="Traceable"),
        trusted_user_id=user_id,
        task_id=task_id,
        run_id=run_id,
    )

    # Memory delete
    await service.forget_memory(
        memory_id=rec.memory_id,
        trusted_user_id=user_id,
        task_id=task_id,
        run_id=run_id,
    )

    events = emitter.get_events_for_run(run_id)
    assert len(events) == 6

    # Verify monotonic sequence numbers
    seqs = [e.sequence_number for e in events]
    assert seqs == [1, 2, 3, 4, 5, 6]

    types = [e.event_type for e in events]
    assert types == [
        ExecutionEventType.RUN_STARTED,
        ExecutionEventType.MEMORY_WRITE_STARTED,
        ExecutionEventType.MEMORY_WRITE_COMPLETED,
        ExecutionEventType.MEMORY_RETRIEVAL_STARTED,
        ExecutionEventType.MEMORY_RETRIEVAL_COMPLETED,
        ExecutionEventType.MEMORY_DELETED,
    ]
