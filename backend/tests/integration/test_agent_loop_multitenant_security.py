"""Integration security tests verifying cross-tenant isolation and identity spoofing prevention."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.schemas.common import utc_now
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_cross_tenant_agent_loop_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # 1. Setup User A and User B
    user_a_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_b_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    user_a = User(id=user_a_id, email="tenant_a@example.com", hashed_password="pw", is_active=True)
    user_b = User(id=user_b_id, email="tenant_b@example.com", hashed_password="pw", is_active=True)

    task_a_id = uuid.uuid4()
    task_b_id = uuid.uuid4()

    task_a = Task(
        id=task_a_id,
        user_id=user_a_id,
        objective="Tenant A task",
        status="running",
        task_metadata={},
    )
    task_b = Task(
        id=task_b_id,
        user_id=user_b_id,
        objective="Tenant B task",
        status="running",
        task_metadata={},
    )

    run_a_id = uuid.uuid4()
    run_b_id = uuid.uuid4()

    run_a = AgentRun(
        id=run_a_id, task_id=task_a_id, run_type="LOOP", status="running", started_at=utc_now()
    )
    run_b = AgentRun(
        id=run_b_id, task_id=task_b_id, run_type="LOOP", status="running", started_at=utc_now()
    )

    db_session.add(user_a)
    db_session.add(user_b)
    db_session.add(task_a)
    db_session.add(task_b)
    db_session.add(run_a)
    db_session.add(run_b)
    await db_session.commit()

    token_a = create_access_token(user_id=user_a_id, email="tenant_a@example.com")
    token_b = create_access_token(user_id=user_b_id, email="tenant_b@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. User A creates an autonomous loop
    create_payload = {
        "task_id": str(task_a_id),
        "run_id": str(run_a_id),
        "objective": "Tenant A bounded calculation: 10 + 20",
    }
    create_res = await async_client.post(
        "/api/v1/agent-loops", json=create_payload, headers=headers_a
    )
    assert create_res.status_code == 201
    loop_a_id = create_res.json()["loop_id"]

    # 3. User B attempts cross-tenant access against User A's loop

    # GET loop
    res_get = await async_client.get(f"/api/v1/agent-loops/{loop_a_id}", headers=headers_b)
    assert res_get.status_code == 404, "User B must receive 404 when accessing User A's loop"

    # POST resume
    res_resume = await async_client.post(
        f"/api/v1/agent-loops/{loop_a_id}/resume",
        json={"additional_iterations": 2},
        headers=headers_b,
    )
    assert res_resume.status_code == 404, "User B must receive 404 when resuming User A's loop"

    # POST cancel
    res_cancel = await async_client.post(
        f"/api/v1/agent-loops/{loop_a_id}/cancel", headers=headers_b
    )
    assert res_cancel.status_code == 404, "User B must receive 404 when cancelling User A's loop"

    # GET iterations
    res_iter = await async_client.get(
        f"/api/v1/agent-loops/{loop_a_id}/iterations", headers=headers_b
    )
    assert res_iter.status_code == 404, "User B must receive 404 when fetching User A's iterations"

    # GET budget
    res_budget = await async_client.get(
        f"/api/v1/agent-loops/{loop_a_id}/budget", headers=headers_b
    )
    assert res_budget.status_code == 404, "User B must receive 404 when viewing User A's budget"

    # GET events
    res_events = await async_client.get(
        f"/api/v1/agent-loops/{loop_a_id}/events", headers=headers_b
    )
    assert res_events.status_code == 404, "User B must receive 404 when fetching User A's events"


@pytest.mark.asyncio
async def test_user_id_spoofing_prevented(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_b_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    user_a = User(
        id=user_a_id, email="user_a_real@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_victim@example.com", hashed_password="pw", is_active=True
    )

    task_b_id = uuid.uuid4()
    task_b = Task(
        id=task_b_id,
        user_id=user_b_id,
        objective="User B private task",
        status="running",
        task_metadata={},
    )

    db_session.add(user_a)
    db_session.add(user_b)
    db_session.add(task_b)
    await db_session.commit()

    # User A presents their valid Bearer token,
    # but attempts to claim User B's identity via X-User-Id header
    token_a = create_access_token(user_id=user_a_id, email="user_a_real@example.com")
    spoofed_headers = {
        "Authorization": f"Bearer {token_a}",
        "X-User-Id": str(user_b_id),
    }

    # Attempt to create a loop targeting User B's task
    create_payload = {
        "task_id": str(task_b_id),
        "run_id": str(uuid.uuid4()),
        "objective": "Malicious loop on victim task",
    }
    res = await async_client.post(
        "/api/v1/agent-loops", json=create_payload, headers=spoofed_headers
    )
    # Must fail with 404 because the authenticated principal is User A, who does NOT own task B
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_idempotency_key_is_scoped_by_authenticated_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_b_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    user_a = User(
        id=user_a_id, email="user_a_idem@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_idem@example.com", hashed_password="pw", is_active=True
    )

    task_a_id = uuid.uuid4()
    task_b_id = uuid.uuid4()

    task_a = Task(
        id=task_a_id, user_id=user_a_id, objective="Task A", status="running", task_metadata={}
    )
    task_b = Task(
        id=task_b_id, user_id=user_b_id, objective="Task B", status="running", task_metadata={}
    )

    run_a_id = uuid.uuid4()
    run_b_id = uuid.uuid4()

    run_a = AgentRun(
        id=run_a_id, task_id=task_a_id, run_type="LOOP", status="running", started_at=utc_now()
    )
    run_b = AgentRun(
        id=run_b_id, task_id=task_b_id, run_type="LOOP", status="running", started_at=utc_now()
    )

    db_session.add(user_a)
    db_session.add(user_b)
    db_session.add(task_a)
    db_session.add(task_b)
    db_session.add(run_a)
    db_session.add(run_b)
    await db_session.commit()

    token_a = create_access_token(user_id=user_a_id, email="user_a_idem@example.com")
    token_b = create_access_token(user_id=user_b_id, email="user_b_idem@example.com")

    shared_idempotency_key = "idempotency-key-shared-123"

    # User A creates loop with idempotency key
    headers_a = {
        "Authorization": f"Bearer {token_a}",
        "Idempotency-Key": shared_idempotency_key,
    }
    payload_a = {
        "task_id": str(task_a_id),
        "run_id": str(run_a_id),
        "objective": "Calculate 1 + 1",
    }
    res_a = await async_client.post("/api/v1/agent-loops", json=payload_a, headers=headers_a)
    assert res_a.status_code == 201
    loop_a_id = res_a.json()["loop_id"]

    # User B sends request with the exact same idempotency key
    headers_b = {
        "Authorization": f"Bearer {token_b}",
        "Idempotency-Key": shared_idempotency_key,
    }
    payload_b = {
        "task_id": str(task_b_id),
        "run_id": str(run_b_id),
        "objective": "Calculate 2 + 2",
    }
    res_b = await async_client.post("/api/v1/agent-loops", json=payload_b, headers=headers_b)
    assert res_b.status_code == 201
    loop_b_id = res_b.json()["loop_id"]

    # Must produce distinct loops; User B must NEVER receive User A's loop
    assert loop_b_id != loop_a_id
