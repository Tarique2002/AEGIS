"""Integration tests for Memory API endpoints."""

import uuid

import pytest
from app.api.v1.endpoints.memory import get_memory_service
from app.main import app
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.manager import MemoryManager
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.semantic.store import SemanticMemoryStore
from app.memory.service import MemoryService
from app.memory.working.store import WorkingMemoryStore
from httpx import AsyncClient
from tests.conftest import TestAsyncSessionLocal
from tests.unit.memory_fakes import FakeQdrantClient, FakeRedisClient


@pytest.fixture(autouse=True)
def override_memory_service():
    """Inject isolated in-memory stores for API testing."""
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
    test_service = MemoryService(manager=manager)

    app.dependency_overrides[get_memory_service] = lambda: test_service
    yield
    app.dependency_overrides.pop(get_memory_service, None)


@pytest.mark.asyncio
async def test_memory_api_lifecycle(async_client: AsyncClient):
    user_id = str(uuid.uuid4())
    headers = {"X-User-Id": user_id}

    # 1. POST /api/v1/memory
    candidate_payload = {
        "content": "API Integration Test: Fast vector retrieval with Qdrant.",
        "memory_type": "semantic",
        "importance": 0.85,
    }
    create_res = await async_client.post("/api/v1/memory", json=candidate_payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    memory_id = created_data["memory_id"]
    assert created_data["content"] == candidate_payload["content"]
    assert created_data["user_id"] == user_id

    # 2. GET /api/v1/memory/{id}
    get_res = await async_client.get(f"/api/v1/memory/{memory_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["memory_id"] == memory_id

    # 3. POST /api/v1/memory/search
    search_payload = {
        "query_text": "Qdrant vector retrieval",
        "limit": 5,
    }
    search_res = await async_client.post(
        "/api/v1/memory/search", json=search_payload, headers=headers
    )
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) >= 1
    assert results[0]["record"]["memory_id"] == memory_id

    # 4. DELETE /api/v1/memory/{id}
    del_res = await async_client.delete(f"/api/v1/memory/{memory_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


@pytest.mark.asyncio
async def test_memory_api_user_isolation(async_client: AsyncClient):
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    # User A creates memory
    create_res = await async_client.post(
        "/api/v1/memory",
        json={"content": "Private secret note for User A", "memory_type": "semantic"},
        headers={"X-User-Id": user_a},
    )
    assert create_res.status_code == 201
    memory_id_a = create_res.json()["memory_id"]

    # User B attempts to access User A's memory by ID -> 404
    get_b_res = await async_client.get(
        f"/api/v1/memory/{memory_id_a}", headers={"X-User-Id": user_b}
    )
    assert get_b_res.status_code == 404

    # User B searches with User A's keywords -> 0 results
    search_b_res = await async_client.post(
        "/api/v1/memory/search",
        json={"query_text": "Private secret note"},
        headers={"X-User-Id": user_b},
    )
    assert search_b_res.status_code == 200
    assert len(search_b_res.json()) == 0
