"""
End-to-End Verification script for AEGIS Phase 3 Multi-Layer Memory Engine.
Demonstrates:
1. Working Memory (Redis key builder, write, read, TTL)
2. Episodic Memory (Experience recording, retrieval, user isolation)
3. Semantic Memory (Vector embedding, semantic retrieval)
4. Deduplication (Exact hash & vector similarity duplicate detection)
5. Multi-Tenant Cross-User Isolation (User A memories invisible to User B)
6. Event Sequencing (Monotonic sequence numbers for memory lifecycle)
7. AgentState Integration (Backward compatibility and context attachment)
"""

import asyncio
import time
import uuid

from app.memory.episodic.repository import EpisodicMemoryRepository
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.manager import MemoryManager
from app.memory.policies import MemoryPolicy
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.schemas import (
    EpisodicMemoryRecord,
    MemoryCandidate,
    MemorySearchQuery,
    MemoryType,
)
from app.memory.semantic.embeddings import MockEmbeddingProvider
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.service import MemoryService
from app.memory.working.store import WorkingMemoryKeyBuilder, WorkingMemoryStore
from app.observability.events import EventEmitter
from app.schemas.state import AgentState, TaskStatus
from tests.unit.memory_fakes import FakeQdrantClient, FakeRedisClient


async def run_verification() -> None:
    print("================================================================================")
    print("           AEGIS PHASE 3 — MULTI-LAYER MEMORY ENGINE E2E VERIFICATION           ")
    print("================================================================================\n")

    # Shared Test Components
    fake_redis = FakeRedisClient()
    fake_qdrant = FakeQdrantClient()
    embedding_provider = MockEmbeddingProvider(dimension=128)
    policy = MemoryPolicy(
        weight_similarity=0.6,
        weight_recency=0.2,
        weight_importance=0.2,
        semantic_dedup_threshold=0.95,
    )

    working_store = WorkingMemoryStore(redis_client=fake_redis)
    semantic_store = SemanticMemoryStore(
        qdrant_client=fake_qdrant,
        embedding_provider=embedding_provider,
        policy=policy,
    )
    procedural_store = ProceduralMemoryStore()

    # In-memory mock episodic store repository
    class InMemoryEpisodicRepo(EpisodicMemoryRepository):
        def __init__(self):
            self.episodes = {}

        async def create_episode(self, session, episode):
            self.episodes[str(episode.episode_id)] = episode
            return type(
                "EpModel",
                (),
                {
                    "id": episode.episode_id,
                    "user_id": episode.user_id,
                    "task_id": episode.task_id,
                    "run_id": episode.run_id,
                    "objective": episode.objective,
                    "summary": episode.summary,
                    "actions": episode.actions,
                    "observations": episode.observations,
                    "result": episode.result,
                    "status": episode.status,
                    "importance": episode.importance,
                    "memory_metadata": episode.metadata,
                    "created_at": episode.created_at,
                    "updated_at": episode.updated_at,
                },
            )()

        async def get_by_id(self, session, episode_id, user_id):
            ep = self.episodes.get(str(episode_id))
            if ep and str(ep.user_id) == str(user_id):
                return await self.create_episode(session, ep)
            return None

        async def search_by_text(self, session, user_id, query, limit=5):
            matched = []
            for ep in self.episodes.values():
                if str(ep.user_id) == str(user_id) and (
                    query.lower() in ep.summary.lower() or query.lower() in ep.objective.lower()
                ):
                    matched.append(await self.create_episode(session, ep))
            return matched[:limit]

    episodic_store = EpisodicMemoryStore(repository=InMemoryEpisodicRepo())

    manager = MemoryManager(
        working_store=working_store,
        episodic_store=episodic_store,
        semantic_store=semantic_store,
        procedural_store=procedural_store,
        policy=policy,
    )
    emitter = EventEmitter()
    service = MemoryService(manager=manager, emitter=emitter, policy=policy)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    task_1 = uuid.uuid4()
    run_1 = uuid.uuid4()

    # --- 1. Working Memory Verification ---
    print("[1/7] Testing Working Memory (Redis Scoped Scratchpad & TTL)...")
    await working_store.set_item(
        user_id=user_a,
        task_id=task_1,
        key="current_context",
        value={"agent_plan_step": 3, "scratch_val": 42},
        ttl_seconds=1,
    )
    working_val = await working_store.get_item(user_a, task_1, "current_context")
    print(f"   [OK] Working Memory Write/Read: {working_val}")
    assert working_val["scratch_val"] == 42

    # Simulate TTL expiration
    redis_key = WorkingMemoryKeyBuilder.build_key(user_a, task_1, "current_context")
    fake_redis._expires[redis_key] = time.time() - 5
    expired_val = await working_store.get_item(user_a, task_1, "current_context")
    print(f"   [OK] TTL Expiration verified: after TTL value is {expired_val}")
    assert expired_val is None

    # --- 2. Episodic Memory Verification ---
    print("\n[2/7] Testing Episodic Memory (Agent Experience Records)...")
    episode = EpisodicMemoryRecord(
        user_id=user_a,
        task_id=task_1,
        run_id=run_1,
        objective="Extract Q3 sales figures",
        summary="Extracted sales numbers from DB and aggregated total to $1.2M.",
        actions=[{"tool": "calculator", "expression": "600000 * 2"}],
        observations=[{"result": 1200000}],
        importance=0.9,
    )
    await episodic_store.record_episode(episode)
    retrieved_ep = await episodic_store.get(episode.episode_id, user_a)
    assert retrieved_ep is not None
    print(
        f"   [OK] Episode stored and retrieved: '{retrieved_ep.content}' "
        f"(importance={retrieved_ep.importance})"
    )

    # --- 3. Semantic Memory Verification ---
    print("\n[3/7] Testing Semantic Memory (Vector Embedding & Retrieval)...")
    sem_cand = MemoryCandidate(
        content="Python is used for machine learning and natural language processing.",
        memory_type=MemoryType.SEMANTIC,
        importance=0.95,
    )
    sem_record = await service.remember(
        candidate=sem_cand,
        trusted_user_id=user_a,
        task_id=task_1,
        run_id=run_1,
    )
    print(f"   [OK] Semantic Memory Stored (ID: {sem_record.memory_id})")

    query = MemorySearchQuery(
        query_text="machine learning programming language",
        memory_types=[MemoryType.SEMANTIC],
        limit=3,
    )
    search_results = await service.recall(
        query=query,
        trusted_user_id=user_a,
        task_id=task_1,
        run_id=run_1,
    )
    print(f"   [OK] Semantic Search returned {len(search_results)} result(s):")
    for res in search_results:
        print(
            f"     - Score: {res.score:.4f} (Sim: {res.similarity_score:.4f}, "
            f"Rec: {res.recency_score:.4f}, Imp: {res.importance_score:.4f})"
        )
        print(f"       Content: '{res.record.content}'")
    assert len(search_results) >= 1
    assert "machine learning" in search_results[0].record.content

    # --- 4. Deduplication Verification ---
    print("\n[4/7] Testing Deduplication (Exact & Semantic Duplicates)...")
    dup_cand = MemoryCandidate(
        content="Python is used for machine learning and natural language processing.",
        memory_type=MemoryType.SEMANTIC,
        importance=0.95,
    )
    dedup_record = await service.remember(
        candidate=dup_cand,
        trusted_user_id=user_a,
        task_id=task_1,
        run_id=run_1,
    )
    print(
        f"   [OK] Duplicate write detected: existing record returned (ID: {dedup_record.memory_id})"
    )
    assert dedup_record.memory_id == sem_record.memory_id

    # --- 5. Multi-Tenant Cross-User Isolation Verification ---
    print("\n[5/7] Testing Cross-User Isolation (User A vs User B)...")
    query_b = MemorySearchQuery(
        query_text="machine learning programming language",
        limit=5,
    )
    results_user_b = await service.recall(
        query=query_b,
        trusted_user_id=user_b,
    )
    print(
        f"   [OK] User B memory search returned {len(results_user_b)} results "
        "(User A data strictly hidden)"
    )
    assert len(results_user_b) == 0

    # --- 6. Event Sequencing Verification ---
    print("\n[6/7] Testing Monotonic Trace Event Sequencing...")
    events = emitter.get_events_for_run(run_1)
    print(f"   [OK] Emitted {len(events)} execution events for run {run_1}:")
    for e in events:
        print(f"     [{e.sequence_number}] {e.event_type.value}: {e.payload}")
    seqs = [e.sequence_number for e in events]
    assert seqs == list(range(1, len(events) + 1)), "Sequence numbers must be strictly contiguous"

    # --- 7. AgentState Backward Compatibility Verification ---
    print("\n[7/7] Testing AgentState Memory Integration...")
    state = AgentState(
        task_id=task_1,
        objective="Demonstrate backward compatibility with memory",
        status=TaskStatus.RUNNING,
    )
    assert len(state.retrieved_memories) == 0, "Phase 1 initial state has 0 memories"

    # Attach retrieved memories
    state.add_retrieved_memories(search_results)
    print(
        f"   [OK] Successfully attached {len(state.retrieved_memories)} memories into "
        "AgentState context:"
    )
    for mem in state.retrieved_memories:
        print(f"     - Type: {mem.memory_type} | Content: '{mem.content}'")
    assert len(state.retrieved_memories) == len(search_results)

    print("\n================================================================================")
    print("        ALL PHASE 3 MEMORY VERIFICATIONS COMPLETED SUCCESSFULLY (100% PASS)     ")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(run_verification())
