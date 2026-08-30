"""Integration tests for Agent Loop REST APIs, tenant isolation, and idempotency."""

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
async def test_agent_loop_api_full_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # 1. Create Users, Task, Run
    user_a = User(id=USER_A_ID, email="loop_a@example.com", hashed_password="pw", is_active=True)
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
        run_type="LOOP",
        status="running",
        started_at=utc_now(),
    )

    db_session.add(user_a)
    db_session.add(task)
    db_session.add(run)
    await db_session.commit()

    headers_user_a = {"X-User-Id": str(USER_A_ID)}
    headers_user_b = {"X-User-Id": str(USER_B_ID)}

    # 2. POST /api/v1/agent-loops (with Idempotency-Key)
    create_payload = {
        "task_id": str(task_id),
        "run_id": str(run_id),
        "objective": "Calculate 25 * 4 and format sentence",
        "autonomy_level": "BOUNDED",
    }
    headers_with_idempotency = {**headers_user_a, "Idempotency-Key": "unique-key-123"}
    create_resp = await async_client.post(
        "/api/v1/agent-loops",
        json=create_payload,
        headers=headers_with_idempotency,
    )
    assert create_resp.status_code == 201, create_resp.text
    loop_data = create_resp.json()
    loop_id = loop_data["loop_id"]
    assert loop_data["status"] == "COMPLETED"
    assert loop_data["iteration_number"] >= 1

    # 3. Idempotency test: Same payload + Idempotency-Key returns existing loop
    idempotent_resp = await async_client.post(
        "/api/v1/agent-loops",
        json=create_payload,
        headers=headers_with_idempotency,
    )
    assert idempotent_resp.status_code == 201
    assert idempotent_resp.json()["loop_id"] == loop_id

    # 4. GET /api/v1/agent-loops/{loop_id} (User A)
    get_resp = await async_client.get(
        f"/api/v1/agent-loops/{loop_id}",
        headers=headers_user_a,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["loop_id"] == loop_id

    # 5. Multi-tenant security: GET /api/v1/agent-loops/{loop_id} by User B must return 404
    get_b_resp = await async_client.get(
        f"/api/v1/agent-loops/{loop_id}",
        headers=headers_user_b,
    )
    assert get_b_resp.status_code == 404

    # 6. GET /api/v1/agent-loops/{loop_id}/iterations
    iter_resp = await async_client.get(
        f"/api/v1/agent-loops/{loop_id}/iterations",
        headers=headers_user_a,
    )
    assert iter_resp.status_code == 200
    iters = iter_resp.json()
    assert len(iters) >= 1

    # 7. GET /api/v1/agent-loops/{loop_id}/budget
    budget_resp = await async_client.get(
        f"/api/v1/agent-loops/{loop_id}/budget",
        headers=headers_user_a,
    )
    assert budget_resp.status_code == 200
    budget_data = budget_resp.json()
    assert "remaining" in budget_data
    assert "limits" in budget_data
