"""Integration tests for orchestration cancellation and state resumption."""

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
async def test_orchestration_cancel_and_resume(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="cancel_user@example.com", hashed_password="pw", is_active=True)
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user_id,
        objective="Cancellation test task",
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

    token = create_access_token(user_id=user_id, email="cancel_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create orchestration
    payload = {
        "task_id": str(task_id),
        "run_id": str(run_id),
        "objective": "Compute 50 * 2",
    }
    create_res = await async_client.post("/api/v1/orchestrations", json=payload, headers=headers)
    assert create_res.status_code == 201
    orch_id = create_res.json()["orchestration_id"]

    # 2. Cancel orchestration
    cancel_res = await async_client.post(
        f"/api/v1/orchestrations/{orch_id}/cancel", headers=headers
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # 3. Resume orchestration
    resume_res = await async_client.post(
        f"/api/v1/orchestrations/{orch_id}/resume",
        json={"rework_reason": "Retry after cancellation"},
        headers=headers,
    )
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "COMPLETED"
