"""Integration security tests verifying cross-tenant isolation in Multi-Agent Orchestration."""

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
async def test_cross_tenant_orchestration_access_forbidden(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # 1. User A and User B
    user_a_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_b_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    user_a = User(
        id=user_a_id, email="user_a_orch@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_orch@example.com", hashed_password="pw", is_active=True
    )

    task_a_id = uuid.uuid4()
    task_a = Task(
        id=task_a_id,
        user_id=user_a_id,
        objective="Tenant A task",
        status="running",
        task_metadata={},
    )

    run_a_id = uuid.uuid4()
    run_a = AgentRun(
        id=run_a_id, task_id=task_a_id, run_type="LOOP", status="running", started_at=utc_now()
    )

    db_session.add(user_a)
    db_session.add(user_b)
    db_session.add(task_a)
    db_session.add(run_a)
    await db_session.commit()

    token_a = create_access_token(user_id=user_a_id, email="user_a_orch@example.com")
    token_b = create_access_token(user_id=user_b_id, email="user_b_orch@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. User A creates orchestration
    payload = {
        "task_id": str(task_a_id),
        "run_id": str(run_a_id),
        "objective": "Tenant A objective: 1 + 2",
    }
    create_res = await async_client.post("/api/v1/orchestrations", json=payload, headers=headers_a)
    assert create_res.status_code == 201
    orch_a_id = create_res.json()["orchestration_id"]

    # 3. User B attempts unauthorized access -> all return 404
    assert (
        await async_client.get(f"/api/v1/orchestrations/{orch_a_id}", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.get(f"/api/v1/orchestrations/{orch_a_id}/workers", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.get(f"/api/v1/orchestrations/{orch_a_id}/results", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.get(f"/api/v1/orchestrations/{orch_a_id}/events", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.get(f"/api/v1/orchestrations/{orch_a_id}/budget", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.post(
            f"/api/v1/orchestrations/{orch_a_id}/resume", json={}, headers=headers_b
        )
    ).status_code == 404
    assert (
        await async_client.post(f"/api/v1/orchestrations/{orch_a_id}/cancel", headers=headers_b)
    ).status_code == 404


@pytest.mark.asyncio
async def test_orchestration_idempotency_scoped_by_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_b_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    user_a = User(
        id=user_a_id, email="user_a_idem2@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_idem2@example.com", hashed_password="pw", is_active=True
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

    token_a = create_access_token(user_id=user_a_id, email="user_a_idem2@example.com")
    token_b = create_access_token(user_id=user_b_id, email="user_b_idem2@example.com")

    shared_key = "idemp-shared-orch-999"

    # User A creates orchestration with idempotency key
    res_a = await async_client.post(
        "/api/v1/orchestrations",
        json={
            "task_id": str(task_a_id),
            "run_id": str(run_a_id),
            "objective": "1 + 1",
            "idempotency_key": shared_key,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a.status_code == 201
    orch_a_id = res_a.json()["orchestration_id"]

    # User B sends request with identical key
    res_b = await async_client.post(
        "/api/v1/orchestrations",
        json={
            "task_id": str(task_b_id),
            "run_id": str(run_b_id),
            "objective": "2 + 2",
            "idempotency_key": shared_key,
        },
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 201
    orch_b_id = res_b.json()["orchestration_id"]

    # Must produce distinct sessions
    assert orch_b_id != orch_a_id
