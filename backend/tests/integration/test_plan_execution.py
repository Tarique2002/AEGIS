"""Integration tests for execution graph events, cancellation, and resume."""

import uuid

import pytest
from app.db.models.event import ExecutionEventModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.schemas.common import utc_now
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TEST_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.mark.asyncio
async def test_plan_execution_events_and_cancellation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=TEST_USER_ID, email="planner_test@example.com", hashed_password="pw", is_active=True
    )
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    task = Task(
        id=task_id,
        user_id=TEST_USER_ID,
        objective="Calculate 50 + 50",
        status="running",
        task_metadata={},
    )
    run = AgentRun(
        id=run_id,
        task_id=task_id,
        run_type="PLANNING",
        status="running",
        started_at=utc_now(),
    )

    db_session.add(user)
    db_session.add(task)
    db_session.add(run)
    await db_session.commit()

    headers = {"X-User-Id": str(TEST_USER_ID)}

    # Create plan
    create_resp = await async_client.post(
        "/api/v1/plans",
        json={"task_id": str(task_id), "run_id": str(run_id), "objective": "Calculate 50 + 50"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["plan_id"]

    # Cancel plan
    cancel_resp = await async_client.post(
        f"/api/v1/plans/{plan_id}/cancel",
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Resume / re-execute plan
    resume_resp = await async_client.post(
        f"/api/v1/plans/{plan_id}/resume",
        headers=headers,
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "COMPLETED"

    # Verify execution events recorded in DB
    events_stmt = (
        select(ExecutionEventModel)
        .where(ExecutionEventModel.run_id == run_id)
        .order_by(ExecutionEventModel.sequence_number.asc())
    )
    events_res = await db_session.execute(events_stmt)
    events = list(events_res.scalars().all())

    event_types = [e.event_type for e in events]
    assert "PLAN_CREATED" in event_types
    assert "PLAN_VALIDATED" in event_types
    assert "GRAPH_EXECUTION_STARTED" in event_types
    assert "GRAPH_EXECUTION_COMPLETED" in event_types
