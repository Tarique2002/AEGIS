"""Unit tests for PostgreSQL-backed EpisodicMemoryStore."""

import uuid

import pytest
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.memory.episodic.store import EpisodicMemoryStore
from app.memory.schemas import EpisodicMemoryRecord
from app.schemas.common import utc_now
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_episodic_memory_store_and_retrieve(db_session: AsyncSession):
    # Setup test user, task, run
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    user = User(id=user_id, email=f"user_{user_id}@test.com", hashed_password="pw")
    task = Task(id=task_id, user_id=user_id, objective="Test episodic objective")
    run = AgentRun(id=run_id, task_id=task_id, run_type="standard", started_at=utc_now())

    db_session.add_all([user, task, run])
    await db_session.flush()

    store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)

    episode = EpisodicMemoryRecord(
        user_id=user_id,
        task_id=task_id,
        run_id=run_id,
        objective="Calculate annual revenue",
        summary="Extracted sales numbers and computed total = $5.2M.",
        actions=[{"action": "calculator", "args": {"expression": "2.6 * 2"}}],
        observations=[{"result": 5.2}],
        result={"revenue": 5.2},
        importance=0.85,
    )

    saved = await store.record_episode(episode, session=db_session)
    assert saved.episode_id == episode.episode_id

    # Retrieve by ID
    retrieved = await store.repository.get_by_id(db_session, episode.episode_id, user_id)
    assert retrieved is not None
    assert retrieved.objective == "Calculate annual revenue"
    assert retrieved.summary == "Extracted sales numbers and computed total = $5.2M."
    assert retrieved.importance == 0.85


@pytest.mark.asyncio
async def test_episodic_memory_user_isolation(db_session: AsyncSession):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    db_session.add(User(id=user_a, email="user_a@test.com", hashed_password="pw"))
    db_session.add(User(id=user_b, email="user_b@test.com", hashed_password="pw"))
    db_session.add(Task(id=task_id, user_id=user_a, objective="Secret task"))
    db_session.add(AgentRun(id=run_id, task_id=task_id, run_type="standard", started_at=utc_now()))
    await db_session.flush()

    store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)
    episode = EpisodicMemoryRecord(
        user_id=user_a,
        task_id=task_id,
        run_id=run_id,
        objective="Top secret mission",
        summary="Confidential output summary",
    )
    await store.record_episode(episode, session=db_session)

    # User A can retrieve
    assert await store.repository.get_by_id(db_session, episode.episode_id, user_a) is not None

    # User B CANNOT retrieve User A's episode
    assert await store.repository.get_by_id(db_session, episode.episode_id, user_b) is None


@pytest.mark.asyncio
async def test_episodic_memory_search(db_session: AsyncSession):
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    db_session.add(User(id=user_id, email="search_user@test.com", hashed_password="pw"))
    db_session.add(Task(id=task_id, user_id=user_id, objective="Search objective"))
    db_session.add(AgentRun(id=run_id, task_id=task_id, run_type="standard", started_at=utc_now()))

    await db_session.flush()

    store = EpisodicMemoryStore(session_factory=TestAsyncSessionLocal)
    episode = EpisodicMemoryRecord(
        user_id=user_id,
        task_id=task_id,
        run_id=run_id,
        objective="Analyze quarterly metrics",
        summary="Generated executive financial deck.",
    )
    await store.record_episode(episode, session=db_session)

    matches = await store.repository.search_by_text(db_session, user_id, "executive financial")
    assert len(matches) == 1
    assert matches[0].id == episode.episode_id

    no_matches = await store.repository.search_by_text(db_session, user_id, "unrelated query")
    assert len(no_matches) == 0
