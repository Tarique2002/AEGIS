"""Comprehensive unit and integration tests for Phase 11 Self-Learning & Agent Evolution Engine."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.learning.evaluator import OutcomeEvaluator
from app.learning.promotion import PromotionManager, PromotionPolicy
from app.learning.sanitizer import sanitize_data
from app.learning.schemas import (
    ExecutionTrajectory,
    LearnedProcedure,
    LearningSignalType,
    OutcomeEvaluationResult,
    ProcedureCandidate,
    StrategyRecommendationQuery,
    TrajectoryCreate,
)
from app.learning.service import SelfLearningService
from app.learning.signals import LearningSignalGenerator
from app.learning.strategy import StrategySelector
from app.schemas.common import utc_now
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# --- 1. Sanitizer Tests ---


def test_sanitizer_redacts_secrets() -> None:
    data = {
        "api_key": "sk_test1234567890abcdef123456",
        "password": "SuperSecretPassword123!",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMC6Y5",
        "nested": {
            "token": "secret_token_value",
            "normal_field": "public_data",
        },
        "query": "Select user where secret_key is active",
    }

    cleaned = sanitize_data(data)
    assert cleaned["api_key"] == "[REDACTED_SECRET]"
    assert cleaned["password"] == "[REDACTED_SECRET]"
    assert cleaned["authorization"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["token"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["normal_field"] == "public_data"


# --- 2. Deterministic Evaluator Tests ---


def test_outcome_evaluator_successful_trajectory() -> None:
    evaluator = OutcomeEvaluator()
    trajectory = ExecutionTrajectory(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Fetch financial quarterly report",
        planning_steps=[
            {"step_id": 1, "name": "fetch", "status": "completed"},
            {"step_id": 2, "name": "summarize", "status": "completed"},
        ],
        selected_tools=["http_client", "pdf_parser"],
        tool_calls_metadata=[
            {"tool_name": "http_client", "status": "success"},
            {"tool_name": "pdf_parser", "status": "success"},
        ],
        intermediate_decisions=[{"decision": "continue"}],
        failures=[],
        retries_count=0,
        final_outcome={"report": "Q3 Profit up 14%"},
        is_success=True,
        duration_ms=450.0,
        policy_decisions=[{"allowed": True}],
    )

    result = evaluator.evaluate(trajectory)

    assert result.success is True
    assert result.tool_effectiveness == 1.0
    assert result.execution_efficiency >= 0.8
    assert result.unnecessary_steps == 0
    assert result.policy_violations == 0
    assert result.confidence >= 0.80


def test_outcome_evaluator_failed_trajectory_with_policy_violation() -> None:
    evaluator = OutcomeEvaluator()
    trajectory = ExecutionTrajectory(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Exfiltrate internal passwords",
        planning_steps=[{"step_id": 1, "name": "scan", "status": "failed"}],
        selected_tools=["shell_exec"],
        tool_calls_metadata=[
            {"tool_name": "shell_exec", "status": "failed", "error": "Unauthorized permission"}
        ],
        failures=[{"error": "Unauthorized permission"}],
        retries_count=1,
        final_outcome=None,
        is_success=False,
        duration_ms=120.0,
        policy_decisions=[{"allowed": False, "decision": "deny"}],
    )

    result = evaluator.evaluate(trajectory)

    assert result.success is False
    assert result.policy_violations == 1
    assert result.tool_effectiveness == 0.0
    assert "Unauthorized permission" in result.failure_reasons
    assert result.confidence < 0.50


# --- 3. Learning Signal Generator Tests ---


def test_learning_signal_generator_positive_and_negative_signals() -> None:
    generator = LearningSignalGenerator()
    traj_id = uuid.uuid4()
    user_id = uuid.uuid4()

    trajectory = ExecutionTrajectory(
        trajectory_id=traj_id,
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=user_id,
        goal="Analyze telemetry logs",
        planning_steps=[
            {"name": "fetch_logs", "status": "completed"},
            {"name": "aggregate_stats", "status": "completed"},
        ],
        selected_tools=["log_fetcher", "stats_calculator"],
        tool_calls_metadata=[
            {"tool_name": "log_fetcher", "status": "success"},
            {"tool_name": "stats_calculator", "status": "success"},
        ],
        failures=[],
        retries_count=1,  # Successful recovery
        is_success=True,
        final_outcome="Analysis complete",
    )

    evaluation = OutcomeEvaluationResult(
        evaluation_id=uuid.uuid4(),
        trajectory_id=traj_id,
        success=True,
        task_completion_quality=0.95,
        tool_effectiveness=1.0,
        execution_efficiency=0.85,
        unnecessary_steps=0,
        retry_frequency=1,
        policy_violations=0,
        confidence=0.90,
    )

    signals = generator.generate_signals(trajectory, evaluation, domain="analytics")
    sig_types = {s.signal_type for s in signals}

    assert LearningSignalType.SUCCESSFUL_TOOL_SEQUENCE in sig_types
    assert LearningSignalType.SUCCESSFUL_PLANNING_PATTERN in sig_types
    assert LearningSignalType.SUCCESSFUL_RECOVERY_STRATEGY in sig_types
    assert all(s.user_id == user_id for s in signals)


def test_learning_signal_generator_multi_agent_delegation() -> None:
    generator = LearningSignalGenerator()
    traj_id = uuid.uuid4()
    user_id = uuid.uuid4()

    trajectory = ExecutionTrajectory(
        trajectory_id=traj_id,
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=user_id,
        goal="Coordinated multi-agent synthesis",
        worker_involvement=[
            {"worker_type": "researcher", "status": "completed", "subtask": "gather info"},
            {
                "worker_type": "synthesis",
                "status": "failed",
                "subtask": "summarize",
                "error": "timeout",
            },
        ],
        is_success=False,
    )

    evaluation = OutcomeEvaluationResult(
        evaluation_id=uuid.uuid4(),
        trajectory_id=traj_id,
        success=False,
        task_completion_quality=0.3,
        tool_effectiveness=0.5,
        execution_efficiency=0.4,
        unnecessary_steps=1,
        retry_frequency=0,
        failure_reasons=["Worker timeout"],
        policy_violations=0,
        confidence=0.3,
    )

    signals = generator.generate_signals(trajectory, evaluation)
    sig_types = {s.signal_type for s in signals}

    assert LearningSignalType.FAILED_DELEGATION_PATTERN in sig_types
    assert LearningSignalType.RECURRING_FAILURE_MODE in sig_types


# --- 4. Promotion Manager & Policy Tests ---


def test_promotion_manager_rejects_low_score() -> None:
    manager = PromotionManager(PromotionPolicy(min_evaluation_score=0.85, min_confidence=0.80))
    user_id = uuid.uuid4()
    candidate = ProcedureCandidate(
        trajectory_id=uuid.uuid4(),
        user_id=user_id,
        name="Suboptimal Strategy",
        description="A strategy that was barely passing",
        ordered_steps=[{"step": 1}],
    )
    evaluation = OutcomeEvaluationResult(
        trajectory_id=candidate.trajectory_id,
        success=True,
        task_completion_quality=0.70,  # Below 0.85
        tool_effectiveness=0.8,
        execution_efficiency=0.75,
        confidence=0.75,  # Below 0.80
    )

    decision, proc = manager.evaluate_and_promote(candidate, evaluation)
    assert decision.promoted is False
    assert proc is None
    assert "Task completion quality" in decision.reason


def test_promotion_manager_accepts_and_versions_procedure() -> None:
    manager = PromotionManager(PromotionPolicy(min_evaluation_score=0.85, min_confidence=0.80))
    user_id = uuid.uuid4()
    candidate = ProcedureCandidate(
        trajectory_id=uuid.uuid4(),
        user_id=user_id,
        name="High Confidence Data Pipeline",
        description="Optimal data pipeline execution strategy",
        ordered_steps=[
            {"step": 1, "action": "extract"},
            {"step": 2, "action": "transform"},
            {"step": 3, "action": "load"},
        ],
        required_tools=["db_query", "transformer"],
    )
    evaluation = OutcomeEvaluationResult(
        trajectory_id=candidate.trajectory_id,
        success=True,
        task_completion_quality=0.95,
        tool_effectiveness=1.0,
        execution_efficiency=0.90,
        policy_violations=0,
        confidence=0.92,
    )

    # Initial promotion (v1)
    decision, proc = manager.evaluate_and_promote(candidate, evaluation)
    assert decision.promoted is True
    assert proc is not None
    assert proc.version == 1
    assert proc.confidence == 0.92
    assert decision.version_transition == "v0 -> v1 (new)"

    # Subsequent update (v2)
    decision2, proc2 = manager.evaluate_and_promote(candidate, evaluation, existing_procedure=proc)
    assert decision2.promoted is True
    assert proc2 is not None
    assert proc2.version == 2
    assert proc2.usage_count == 2
    assert proc2.success_count == 2
    assert decision2.version_transition == "v1 -> v2"


# --- 5. Strategy Selector Tests ---


def test_strategy_selector_ranking_and_tenant_isolation() -> None:
    selector = StrategySelector()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    proc_a1 = LearnedProcedure(
        procedure_id=uuid.uuid4(),
        user_id=user_a,
        task_domain="analytics",
        name="Query and aggregate user billing metrics",
        description="Extract billing entries and run aggregations",
        trigger_conditions=["billing metrics"],
        ordered_steps=[{"step": 1}],
        required_tools=["sql_client"],
        confidence=0.90,
        usage_count=10,
        success_count=9,
        version=1,
    )

    proc_a2 = LearnedProcedure(
        procedure_id=uuid.uuid4(),
        user_id=user_a,
        task_domain="analytics",
        name="Send notification emails",
        description="Notify customers of system updates",
        trigger_conditions=["email notification"],
        ordered_steps=[{"step": 1}],
        required_tools=["email_tool"],
        confidence=0.85,
        usage_count=5,
        success_count=4,
        version=1,
    )

    proc_b = LearnedProcedure(
        procedure_id=uuid.uuid4(),
        user_id=user_b,  # Belongs to tenant B!
        task_domain="analytics",
        name="Query and aggregate user billing metrics for B",
        description="Extract billing entries for tenant B",
        trigger_conditions=["billing metrics"],
        ordered_steps=[{"step": 1}],
        required_tools=["sql_client"],
        confidence=0.99,
        usage_count=50,
        success_count=50,
        version=3,
    )

    query = StrategyRecommendationQuery(
        objective="Calculate billing metrics for the last quarter",
        available_tools=["sql_client"],
        limit=5,
    )

    # Query for User A
    recs = selector.rank_procedures(query, [proc_a1, proc_a2, proc_b], user_id=user_a)

    assert len(recs) == 1
    assert recs[0].procedure_id == proc_a1.procedure_id
    assert recs[0].match_score > 0.5
    # Tenant B procedure must NOT leak to Tenant A
    assert all(r.procedure_id != proc_b.procedure_id for r in recs)


# --- 6. End-to-End SelfLearningService Integration with Database ---


@pytest.mark.asyncio
async def test_self_learning_service_end_to_end(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    # Create baseline user, task, and run in DB
    user = User(id=user_id, email=f"learner_{user_id}@test.com", hashed_password="pw")
    task = Task(id=task_id, user_id=user_id, objective="Process order batch")
    run = AgentRun(id=run_id, task_id=task_id, run_type="standard", started_at=utc_now())

    db_session.add_all([user, task, run])
    await db_session.flush()

    service = SelfLearningService()

    traj_create = TrajectoryCreate(
        task_id=task_id,
        run_id=run_id,
        goal="Process order batch efficiently",
        planning_steps=[
            {"step_id": 1, "name": "validate_orders", "status": "completed"},
            {"step_id": 2, "name": "dispatch_orders", "status": "completed"},
        ],
        selected_tools=["validator", "dispatcher"],
        tool_calls_metadata=[
            {"tool_name": "validator", "status": "success"},
            {"tool_name": "dispatcher", "status": "success"},
        ],
        intermediate_decisions=[{"action": "dispatch"}],
        failures=[],
        retries_count=0,
        final_outcome={"processed_orders": 42},
        is_success=True,
        duration_ms=320.0,
        policy_decisions=[{"allowed": True}],
    )

    trajectory, eval_res, signals, decision = await service.process_completed_run(
        create_data=traj_create,
        trusted_user_id=user_id,
        session=db_session,
        domain="orders",
    )
    await db_session.commit()

    assert trajectory.task_id == task_id
    assert eval_res.success is True
    assert len(signals) >= 2
    assert decision is not None
    assert decision.promoted is True

    # Check trajectory inspection
    fetched_traj = await service.get_trajectory(trajectory.trajectory_id, user_id, db_session)
    assert fetched_traj is not None
    assert fetched_traj.goal == "Process order batch efficiently"

    # Check recommendation
    rec_query = StrategyRecommendationQuery(objective="Process order batch")
    rec_resp = await service.recommend_strategies(rec_query, user_id, db_session)
    assert rec_resp.total_matches >= 1
    assert rec_resp.recommendations[0].name.startswith("Strategy: Process order batch")

    # Check stats
    stats = await service.get_learning_stats(user_id, db_session)
    assert stats.total_trajectories == 1
    assert stats.successful_trajectories == 1
    assert stats.total_signals >= 2
    assert stats.active_procedures >= 1

    # Check deprecation
    proc_id = decision.procedure_id
    assert proc_id is not None
    dep_success = await service.deprecate_procedure(proc_id, user_id, db_session)
    assert dep_success is True
    await db_session.commit()

    rec_after = await service.recommend_strategies(rec_query, user_id, db_session)
    assert rec_after.total_matches == 0  # Deprecated procedure excluded


# --- 7. REST API Integration Tests ---


@pytest.mark.asyncio
async def test_learning_api_endpoints(async_client: AsyncClient, db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    user = User(id=user_id, email=f"api_user_{user_id}@test.com", hashed_password="pw")
    task = Task(id=uuid.uuid4(), user_id=user_id, objective="API Test Task")
    run = AgentRun(id=uuid.uuid4(), task_id=task.id, run_type="standard", started_at=utc_now())

    db_session.add_all([user, task, run])
    await db_session.commit()

    token = create_access_token(user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. POST /api/v1/learning/trajectories
    create_payload = {
        "task_id": str(task.id),
        "run_id": str(run.id),
        "goal": "Generate quarterly summary report",
        "planning_steps": [
            {"step_id": 1, "name": "gather", "status": "completed"},
            {"step_id": 2, "name": "format", "status": "completed"},
        ],
        "selected_tools": ["db_query", "chart_gen"],
        "tool_calls_metadata": [
            {"tool_name": "db_query", "status": "success"},
            {"tool_name": "chart_gen", "status": "success"},
        ],
        "intermediate_decisions": [],
        "failures": [],
        "retries_count": 0,
        "final_outcome": {"chart": "url"},
        "is_success": True,
        "duration_ms": 250.0,
        "policy_decisions": [],
    }

    resp = await async_client.post(
        "/api/v1/learning/trajectories", json=create_payload, headers=headers
    )
    assert resp.status_code == 201
    traj_data = resp.json()
    trajectory_id = traj_data["trajectory_id"]
    assert traj_data["goal"] == "Generate quarterly summary report"

    # 2. GET /api/v1/learning/trajectories
    resp = await async_client.get("/api/v1/learning/trajectories", headers=headers)
    assert resp.status_code == 200
    trajs = resp.json()
    assert len(trajs) >= 1
    assert any(t["trajectory_id"] == trajectory_id for t in trajs)

    # 3. GET /api/v1/learning/trajectories/{id}
    resp = await async_client.get(f"/api/v1/learning/trajectories/{trajectory_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["trajectory_id"] == trajectory_id

    # 4. GET /api/v1/learning/trajectories/{id}/evaluation
    resp = await async_client.get(
        f"/api/v1/learning/trajectories/{trajectory_id}/evaluation", headers=headers
    )
    assert resp.status_code == 200
    eval_json = resp.json()
    assert eval_json["success"] is True
    assert eval_json["task_completion_quality"] >= 0.85

    # 5. GET /api/v1/learning/signals
    resp = await async_client.get("/api/v1/learning/signals", headers=headers)
    assert resp.status_code == 200
    signals = resp.json()
    assert len(signals) >= 1

    # 6. GET /api/v1/learning/procedures
    resp = await async_client.get("/api/v1/learning/procedures", headers=headers)
    assert resp.status_code == 200
    procs = resp.json()
    assert len(procs) >= 1
    proc_id = procs[0]["procedure_id"]

    # 7. GET /api/v1/learning/procedures/{id}
    resp = await async_client.get(f"/api/v1/learning/procedures/{proc_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["procedure_id"] == proc_id

    # 8. POST /api/v1/learning/procedures/recommend
    rec_payload = {"objective": "Generate quarterly summary report"}
    resp = await async_client.post(
        "/api/v1/learning/procedures/recommend", json=rec_payload, headers=headers
    )
    assert resp.status_code == 200
    rec_json = resp.json()
    assert rec_json["total_matches"] >= 1

    # 9. GET /api/v1/learning/stats
    resp = await async_client.get("/api/v1/learning/stats", headers=headers)
    assert resp.status_code == 200
    stats_json = resp.json()
    assert stats_json["total_trajectories"] >= 1
    assert stats_json["successful_trajectories"] >= 1

    # 10. POST /api/v1/learning/procedures/{id}/deprecate
    resp = await async_client.post(
        f"/api/v1/learning/procedures/{proc_id}/deprecate", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["deprecated"] is True


@pytest.mark.asyncio
async def test_learning_api_tenant_isolation(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    db_session.add_all(
        [
            User(id=user_a, email="user_a@test.com", hashed_password="pw"),
            User(id=user_b, email="user_b@test.com", hashed_password="pw"),
        ]
    )
    await db_session.commit()

    token_a = create_access_token(user_id=user_a)
    token_b = create_access_token(user_id=user_b)

    task_a = Task(id=uuid.uuid4(), user_id=user_a, objective="Task for A")
    run_a = AgentRun(id=uuid.uuid4(), task_id=task_a.id, run_type="standard", started_at=utc_now())
    db_session.add_all([task_a, run_a])
    await db_session.commit()

    # User A records trajectory
    resp = await async_client.post(
        "/api/v1/learning/trajectories",
        json={
            "task_id": str(task_a.id),
            "run_id": str(run_a.id),
            "goal": "Secret tenant A business process",
            "is_success": True,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201
    traj_id = resp.json()["trajectory_id"]

    # User B attempts to access User A's trajectory -> 404
    resp_b = await async_client.get(
        f"/api/v1/learning/trajectories/{traj_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 404

    # User B listing trajectories must be empty
    resp_b_list = await async_client.get(
        "/api/v1/learning/trajectories",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b_list.status_code == 200
    assert len(resp_b_list.json()) == 0
