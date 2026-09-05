"""Integration tests for Phase 11 Multi-Tenant Security Boundaries & Self-Learning Engine."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.learning import LearnedProcedureModel, TrajectoryModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.learning.schemas import PromotionStatus
from app.schemas.common import utc_now
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_cross_tenant_trajectory_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User A cannot access User B's trajectory or its evaluation -> Returns 404."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="user_a_learning@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_learning@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])

    task_b = Task(id=uuid.uuid4(), user_id=user_b_id, objective="User B Task")
    run_b = AgentRun(
        id=uuid.uuid4(),
        task_id=task_b.id,
        run_type="EXECUTION",
        status="COMPLETED",
        started_at=utc_now(),
    )
    db_session.add_all([task_b, run_b])

    traj_b = TrajectoryModel(
        id=uuid.uuid4(),
        user_id=user_b_id,
        task_id=task_b.id,
        run_id=run_b.id,
        goal="Extract confidential financial statistics",
        planning_steps=[{"step": 1, "description": "Query private records"}],
        selected_tools=["database_tool"],
        tool_calls_metadata=[{"tool": "database_tool", "duration_ms": 45.0}],
        worker_involvement=[],
        intermediate_decisions=[],
        failures=[],
        retries_count=0,
        final_outcome={"result": "Sensitive financial report"},
        is_success=True,
        duration_ms=450.0,
        tokens_used=1200,
        trajectory_metadata={"confidential": True},
    )
    db_session.add(traj_b)
    await db_session.commit()

    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a_learning@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # User A tries to GET User B's trajectory details
    resp_traj = await async_client.get(
        f"/api/v1/learning/trajectories/{traj_b.id}",
        headers=headers_a,
    )
    assert resp_traj.status_code == 404
    assert "not found" in resp_traj.json()["detail"].lower()

    # User A tries to GET evaluation of User B's trajectory
    resp_eval = await async_client.get(
        f"/api/v1/learning/trajectories/{traj_b.id}/evaluation",
        headers=headers_a,
    )
    assert resp_eval.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_signals_list_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Listing signals only returns signals for the requesting tenant."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="user_a_sig@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_sig@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    # Create trajectory for User B via API
    task_b = Task(id=uuid.uuid4(), user_id=user_b_id, objective="User B Task")
    run_b = AgentRun(
        id=uuid.uuid4(),
        task_id=task_b.id,
        run_type="EXECUTION",
        status="COMPLETED",
        started_at=utc_now(),
    )
    db_session.add_all([task_b, run_b])
    await db_session.commit()

    token_b = create_access_token(
        user_id=user_b_id,
        email="user_b_sig@example.com",
        roles=["DEVELOPER"],
        scopes=["task:write"],
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    create_payload = {
        "task_id": str(task_b.id),
        "run_id": str(run_b.id),
        "goal": "Analyze tenant B proprietary signals",
        "selected_tools": ["analysis_tool"],
        "tool_calls_metadata": [{"tool": "analysis_tool", "duration_ms": 10.0}],
        "is_success": True,
        "duration_ms": 150.0,
    }
    resp_post = await async_client.post(
        "/api/v1/learning/trajectories",
        json=create_payload,
        headers=headers_b,
    )
    assert resp_post.status_code == 201

    # User A lists signals
    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a_sig@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_a = await async_client.get("/api/v1/learning/signals", headers=headers_a)
    assert resp_a.status_code == 200
    assert len(resp_a.json()) == 0

    # User B lists signals
    resp_b = await async_client.get("/api/v1/learning/signals", headers=headers_b)
    assert resp_b.status_code == 200
    assert len(resp_b.json()) >= 1


@pytest.mark.asyncio
async def test_cross_tenant_procedure_access_and_deprecation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User A cannot access or deprecate User B's private procedure -> Returns 404."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="user_a_proc@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_proc@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])

    proc_b = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_b_id,
        task_domain="devops",
        name="Private Production Deployment Procedure",
        description="Proprietary deployment strategy for User B microservices",
        trigger_conditions=["deploy", "production"],
        ordered_steps=[{"step": 1, "action": "deploy_canary"}],
        required_tools=["deploy_tool"],
        constraints=["require_approval"],
        success_criteria=["zero_downtime"],
        confidence=0.95,
        status=PromotionStatus.PROMOTED.value,
        is_global=False,
        procedure_metadata={"proprietary": True},
    )
    db_session.add(proc_b)
    await db_session.commit()

    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a_proc@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # User A tries to GET User B's procedure
    resp_get = await async_client.get(
        f"/api/v1/learning/procedures/{proc_b.id}",
        headers=headers_a,
    )
    assert resp_get.status_code == 404

    # User A tries to DEPRECATE User B's procedure
    resp_dep = await async_client.post(
        f"/api/v1/learning/procedures/{proc_b.id}/deprecate",
        headers=headers_a,
    )
    assert resp_dep.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_strategy_recommendations_quarantine(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Recommendations strictly quarantine private procedures of other tenants."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="user_a_rec@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="user_b_rec@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])

    # User B private procedure
    proc_b = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_b_id,
        task_domain="cloud",
        name="Kubernetes Rolling Upgrade",
        description="Upgrades microservice pods on Kubernetes cluster gracefully",
        trigger_conditions=["kubernetes", "upgrade", "cluster"],
        ordered_steps=[{"step": 1, "action": "kubectl_rollout"}],
        required_tools=["kubectl"],
        constraints=[],
        success_criteria=[],
        confidence=0.99,
        status=PromotionStatus.PROMOTED.value,
        is_global=False,
        procedure_metadata={},
    )
    # Global procedure available to all
    proc_global = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_b_id,
        task_domain="general",
        name="Standard HTTP Retry Strategy",
        description="Standard exponential backoff retry pattern for HTTP calls",
        trigger_conditions=["http", "retry", "network"],
        ordered_steps=[{"step": 1, "action": "retry_backoff"}],
        required_tools=[],
        constraints=[],
        success_criteria=[],
        confidence=0.90,
        status=PromotionStatus.PROMOTED.value,
        is_global=True,
        procedure_metadata={},
    )
    db_session.add_all([proc_b, proc_global])
    await db_session.commit()

    token_a = create_access_token(
        user_id=user_a_id,
        email="user_a_rec@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # User A queries for Kubernetes procedure -> Should return NO recommendations
    resp_rec_b = await async_client.post(
        "/api/v1/learning/procedures/recommend",
        json={"objective": "Upgrade Kubernetes cluster microservice"},
        headers=headers_a,
    )
    assert resp_rec_b.status_code == 200
    recs_k8s = resp_rec_b.json()["recommendations"]
    proc_ids = [r["procedure_id"] for r in recs_k8s]
    assert str(proc_b.id) not in proc_ids

    # User A queries for HTTP retry -> Global procedure is recommended
    resp_rec_global = await async_client.post(
        "/api/v1/learning/procedures/recommend",
        json={"objective": "Standard HTTP retry backoff request"},
        headers=headers_a,
    )
    assert resp_rec_global.status_code == 200
    recs_http = resp_rec_global.json()["recommendations"]
    assert any(r["procedure_id"] == str(proc_global.id) for r in recs_http)


@pytest.mark.asyncio
async def test_trajectory_data_sanitization_defense(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Proves sensitive credentials and tokens are scrubbed upon trajectory ingestion."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="user_sanitizer@example.com", hashed_password="pw", is_active=True
    )
    task = Task(id=uuid.uuid4(), user_id=user_id, objective="Testing security sanitization")
    run = AgentRun(
        id=uuid.uuid4(),
        task_id=task.id,
        run_type="EXECUTION",
        status="COMPLETED",
        started_at=utc_now(),
    )
    db_session.add_all([user, task, run])
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="user_sanitizer@example.com",
        roles=["DEVELOPER"],
        scopes=["task:write"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "task_id": str(task.id),
        "run_id": str(run.id),
        "goal": "Deploy app with token sk-ant-api03-abcdef1234567890abcdef12 and secret pass",
        "planning_steps": [
            {
                "step": 1,
                "command": "login --password SuperSecretPassword123!",
                "auth_header": (
                    "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW4ifQ.abc"
                ),
            }
        ],
        "tool_calls_metadata": [
            {
                "tool": "bash",
                "env": {
                    "OPENAI_API_KEY": "sk-proj-1234567890abcdef1234567890",
                    "DATABASE_URL": "postgres://admin:TopSecretPass99@db:5432/prod",
                },
            }
        ],
        "final_outcome": {"api_key": "sk-test-secret-value-12345", "status": "ok"},
        "is_success": True,
        "duration_ms": 250.0,
    }

    resp = await async_client.post(
        "/api/v1/learning/trajectories",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()

    # Verify no raw secrets survived
    raw_json_str = str(data)
    assert "SuperSecretPassword123!" not in raw_json_str
    assert "sk-proj-1234567890abcdef1234567890" not in raw_json_str
    assert "sk-ant-api03-abcdef1234567890abcdef12" not in raw_json_str
    assert "TopSecretPass99" not in raw_json_str
    assert "[REDACTED" in raw_json_str
