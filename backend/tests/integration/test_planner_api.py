"""Integration tests for Planner & Execution Graph API endpoints and tenant isolation."""

import uuid

import pytest
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.schemas.common import utc_now
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_planner_api_full_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # 1. Create User A, Task, Run
    user_a = User(id=USER_A_ID, email="user_a@example.com", hashed_password="pw", is_active=True)
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    task = Task(
        id=task_id,
        user_id=USER_A_ID,
        objective="Calculate 25 * 4 and format",
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

    db_session.add(user_a)
    db_session.add(task)
    db_session.add(run)
    await db_session.commit()

    headers_user_a = {"X-User-Id": str(USER_A_ID)}
    headers_user_b = {"X-User-Id": str(USER_B_ID)}

    # 2. POST /api/v1/plans
    create_payload = {
        "task_id": str(task_id),
        "run_id": str(run_id),
        "objective": "Calculate 25 * 4 and format sentence",
    }
    create_resp = await async_client.post(
        "/api/v1/plans",
        json=create_payload,
        headers=headers_user_a,
    )
    assert create_resp.status_code == 201, create_resp.text
    plan_data = create_resp.json()
    plan_id = plan_data["plan_id"]
    assert plan_data["status"] == "VALIDATED"
    assert len(plan_data["nodes"]) >= 2

    # 3. GET /api/v1/plans/{plan_id} (User A)
    get_resp = await async_client.get(
        f"/api/v1/plans/{plan_id}",
        headers=headers_user_a,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["plan_id"] == plan_id

    # 4. Multi-tenant security: GET /api/v1/plans/{plan_id} by User B must return 404
    get_b_resp = await async_client.get(
        f"/api/v1/plans/{plan_id}",
        headers=headers_user_b,
    )
    assert get_b_resp.status_code == 404

    # 5. POST /api/v1/plans/{plan_id}/execute (User A)
    exec_resp = await async_client.post(
        f"/api/v1/plans/{plan_id}/execute",
        json={},
        headers=headers_user_a,
    )
    assert exec_resp.status_code == 200, exec_resp.text
    exec_data = exec_resp.json()
    assert exec_data["status"] == "COMPLETED"
    assert exec_data["final_output"] == "The result is 100."
