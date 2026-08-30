"""Integration tests for Evaluation & Reflection API endpoints and tenant security."""

import uuid
from datetime import UTC, datetime

import pytest
from app.db.models.event import ExecutionEventModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_task_and_run(
    session: AsyncSession,
    user_id: uuid.UUID,
    task_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    status: str = "completed",
    result: str = "100",
) -> tuple[Task, AgentRun]:
    t_id = task_id or uuid.uuid4()
    r_id = run_id or uuid.uuid4()
    now = datetime.now(UTC)

    task = Task(
        id=t_id,
        user_id=user_id,
        objective="Calculate 25 * 4",
        status=status,
        result=result,
        task_metadata={},
        completed_at=now,
    )
    run = AgentRun(
        id=r_id,
        task_id=t_id,
        run_type="EXECUTION",
        model_used="test-model",
        prompt_tokens=50,
        completion_tokens=20,
        total_tokens=70,
        latency_ms=120.0,
        status=status,
        result=result,
        started_at=now,
        ended_at=now,
    )
    ev = ExecutionEventModel(
        task_id=t_id,
        run_id=r_id,
        event_type="RUN_COMPLETED",
        sequence_number=1,
        payload={"result": result},
        timestamp=now,
    )
    session.add(task)
    session.add(run)
    session.add(ev)
    await session.commit()
    return task, run


@pytest.mark.asyncio
async def test_evaluation_and_reflection_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a = uuid.uuid4()
    headers_a = {"X-User-Id": str(user_a)}

    task, run = await _seed_task_and_run(
        session=db_session,
        user_id=user_a,
        result="100",
    )

    # 1. POST /api/v1/evaluations
    eval_req = {
        "task_id": str(task.id),
        "run_id": str(run.id),
        "expected_result": "100",
        "actual_result": "100",
    }
    eval_res = await async_client.post("/api/v1/evaluations", json=eval_req, headers=headers_a)
    assert eval_res.status_code == 201
    eval_data = eval_res.json()
    evaluation_id = eval_data["evaluation_id"]
    assert eval_data["passed"] is True
    assert eval_data["overall_score"] >= 0.70

    # 2. GET /api/v1/evaluations/{evaluation_id}
    get_eval_res = await async_client.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers_a)
    assert get_eval_res.status_code == 200
    assert get_eval_res.json()["evaluation_id"] == evaluation_id

    # 3. GET /api/v1/tasks/{task_id}/evaluations
    task_evals_res = await async_client.get(
        f"/api/v1/tasks/{task.id}/evaluations", headers=headers_a
    )
    assert task_evals_res.status_code == 200
    task_evals = task_evals_res.json()
    assert len(task_evals) == 1
    assert task_evals[0]["evaluation_id"] == evaluation_id

    # 4. POST /api/v1/evaluations/{evaluation_id}/reflection
    ref_req = {"metadata": {"source": "integration_test"}, "persist_to_memory": False}
    ref_res = await async_client.post(
        f"/api/v1/evaluations/{evaluation_id}/reflection",
        json=ref_req,
        headers=headers_a,
    )
    assert ref_res.status_code == 201
    ref_data = ref_res.json()
    assert ref_data["evaluation_id"] == evaluation_id
    assert ref_data["confidence"] == 1.0

    # 5. GET /api/v1/evaluations/{evaluation_id}/reflection
    get_ref_res = await async_client.get(
        f"/api/v1/evaluations/{evaluation_id}/reflection",
        headers=headers_a,
    )
    assert get_ref_res.status_code == 200
    assert get_ref_res.json()["evaluation_id"] == evaluation_id


@pytest.mark.asyncio
async def test_tenant_security_cross_user_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    headers_a = {"X-User-Id": str(user_a)}
    headers_b = {"X-User-Id": str(user_b)}

    task, run = await _seed_task_and_run(
        session=db_session,
        user_id=user_a,
        result="User A private output",
    )

    # User A creates an evaluation
    eval_req = {
        "task_id": str(task.id),
        "run_id": str(run.id),
    }
    eval_res = await async_client.post("/api/v1/evaluations", json=eval_req, headers=headers_a)
    assert eval_res.status_code == 201
    evaluation_id = eval_res.json()["evaluation_id"]

    # User A creates reflection
    ref_res = await async_client.post(
        f"/api/v1/evaluations/{evaluation_id}/reflection",
        json={},
        headers=headers_a,
    )
    assert ref_res.status_code == 201

    # User B attempts to access User A's evaluation -> 404 NOT FOUND (no leak)
    b_eval_res = await async_client.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers_b)
    assert b_eval_res.status_code == 404

    # User B attempts to list User A's task evaluations -> 404 NOT FOUND
    b_task_evals_res = await async_client.get(
        f"/api/v1/tasks/{task.id}/evaluations", headers=headers_b
    )
    assert b_task_evals_res.status_code == 404

    # User B attempts to generate reflection on User A's evaluation -> 404 NOT FOUND
    b_gen_ref_res = await async_client.post(
        f"/api/v1/evaluations/{evaluation_id}/reflection",
        json={},
        headers=headers_b,
    )
    assert b_gen_ref_res.status_code == 404

    # User B attempts to retrieve User A's reflection -> 404 NOT FOUND
    b_get_ref_res = await async_client.get(
        f"/api/v1/evaluations/{evaluation_id}/reflection",
        headers=headers_b,
    )
    assert b_get_ref_res.status_code == 404
