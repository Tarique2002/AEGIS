"""Integration tests for Multi-Agent Orchestration REST API endpoints."""

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
async def test_orchestration_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # 1. Seed user, task, run
    user_id = uuid.uuid4()
    user = User(id=user_id, email="orchestrator@example.com", hashed_password="pw", is_active=True)
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user_id,
        objective="Calculate 10 + 20",
        status="running",
        task_metadata={},
    )
    run_id = uuid.uuid4()
    run = AgentRun(
        id=run_id, task_id=task_id, run_type="LOOP", status="running", started_at=utc_now()
    )

    db_session.add(user)
    db_session.add(task)
    db_session.add(run)
    await db_session.commit()

    token = create_access_token(user_id=user_id, email="orchestrator@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. POST /api/v1/orchestrations
    payload = {
        "task_id": str(task_id),
        "run_id": str(run_id),
        "objective": "Calculate 10 + 20 and verify result",
    }
    create_res = await async_client.post("/api/v1/orchestrations", json=payload, headers=headers)
    assert create_res.status_code == 201
    orch_data = create_res.json()
    orch_id = orch_data["orchestration_id"]
    assert orch_data["status"] == "COMPLETED"
    assert orch_data["tasks_count"] == 3

    # 3. GET /api/v1/orchestrations/{id}
    get_res = await async_client.get(f"/api/v1/orchestrations/{orch_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["orchestration_id"] == orch_id

    # 4. GET /api/v1/orchestrations/{id}/workers
    workers_res = await async_client.get(
        f"/api/v1/orchestrations/{orch_id}/workers", headers=headers
    )
    assert workers_res.status_code == 200
    assert len(workers_res.json()) == 3

    # 5. GET /api/v1/orchestrations/{id}/results
    results_res = await async_client.get(
        f"/api/v1/orchestrations/{orch_id}/results", headers=headers
    )
    assert results_res.status_code == 200
    assert "worker_contributions" in results_res.json()

    # 6. GET /api/v1/orchestrations/{id}/events
    events_res = await async_client.get(f"/api/v1/orchestrations/{orch_id}/events", headers=headers)
    assert events_res.status_code == 200
    assert len(events_res.json()) >= 2

    # 7. GET /api/v1/orchestrations/{id}/budget
    budget_res = await async_client.get(f"/api/v1/orchestrations/{orch_id}/budget", headers=headers)
    assert budget_res.status_code == 200
    assert "remaining" in budget_res.json()
