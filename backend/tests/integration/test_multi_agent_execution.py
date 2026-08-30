"""Integration tests for multi-agent parallel and DAG execution pipelines."""

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
async def test_multi_agent_dag_execution(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email="dag_user@example.com", hashed_password="pw", is_active=True)
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user_id,
        objective="Multi-agent quantitative task",
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

    token = create_access_token(user_id=user_id, email="dag_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "task_id": str(task_id),
        "run_id": str(run_id),
        "objective": "Calculate numbers 10, 20, and 30",
    }
    res = await async_client.post("/api/v1/orchestrations", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["completed_tasks_count"] == 3
