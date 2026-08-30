"""Unit tests for Redis-backed WorkingMemoryStore."""

import time
import uuid

import pytest
from app.memory.working.store import WorkingMemoryKeyBuilder, WorkingMemoryStore
from tests.unit.memory_fakes import FakeRedisClient


@pytest.mark.asyncio
async def test_working_memory_key_builder():
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    key = "scratch_calc"

    constructed = WorkingMemoryKeyBuilder.build_key(user_id, task_id, key)
    assert constructed == f"aegis:memory:working:{user_id}:{task_id}:{key}"

    pattern = WorkingMemoryKeyBuilder.build_task_pattern(user_id, task_id)
    assert pattern == f"aegis:memory:working:{user_id}:{task_id}:*"


@pytest.mark.asyncio
async def test_working_memory_set_get_delete():
    fake_redis = FakeRedisClient()
    store = WorkingMemoryStore(redis_client=fake_redis)

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    # Set
    await store.set_item(user_id, task_id, "step_state", {"completed_substeps": [1, 2]})

    # Get
    retrieved = await store.get_item(user_id, task_id, "step_state")
    assert retrieved == {"completed_substeps": [1, 2]}

    # Delete
    deleted = await store.delete_item(user_id, task_id, "step_state")
    assert deleted is True

    # Get after delete
    assert await store.get_item(user_id, task_id, "step_state") is None


@pytest.mark.asyncio
async def test_working_memory_ttl_expiration():
    fake_redis = FakeRedisClient()
    store = WorkingMemoryStore(redis_client=fake_redis)

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    # Set with 1 second TTL
    await store.set_item(user_id, task_id, "temp_token", "secret123", ttl_seconds=1)

    # Immediately available
    assert await store.get_item(user_id, task_id, "temp_token") == "secret123"

    # Manually advance time by updating expiration
    fake_redis._expires[WorkingMemoryKeyBuilder.build_key(user_id, task_id, "temp_token")] = (
        time.time() - 1
    )

    # After expiration -> None
    assert await store.get_item(user_id, task_id, "temp_token") is None


@pytest.mark.asyncio
async def test_working_memory_task_and_user_isolation():
    fake_redis = FakeRedisClient()
    store = WorkingMemoryStore(redis_client=fake_redis)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    task_1 = uuid.uuid4()
    task_2 = uuid.uuid4()

    # User A Task 1 vs User B Task 1
    await store.set_item(user_a, task_1, "var", "val_user_a")
    await store.set_item(user_b, task_1, "var", "val_user_b")

    assert await store.get_item(user_a, task_1, "var") == "val_user_a"
    assert await store.get_item(user_b, task_1, "var") == "val_user_b"

    # User A Task 1 vs User A Task 2
    await store.set_item(user_a, task_2, "var", "val_task_2")
    assert await store.get_item(user_a, task_1, "var") == "val_user_a"
    assert await store.get_item(user_a, task_2, "var") == "val_task_2"


@pytest.mark.asyncio
async def test_working_memory_clear_task():
    fake_redis = FakeRedisClient()
    store = WorkingMemoryStore(redis_client=fake_redis)

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    await store.set_item(user_id, task_id, "k1", "v1")
    await store.set_item(user_id, task_id, "k2", "v2")
    await store.set_item(user_id, uuid.uuid4(), "other_task", "preserve_me")

    cleared = await store.clear_task_memory(user_id, task_id)
    assert cleared == 2

    assert await store.get_item(user_id, task_id, "k1") is None
    assert await store.get_item(user_id, task_id, "k2") is None
