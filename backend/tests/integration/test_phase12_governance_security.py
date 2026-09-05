"""Integration tests for Phase 12 Production Learning Governance & Multi-Tenant Security."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.learning import (
    LearnedProcedureModel,
    LearnedProcedureVersionModel,
    TrajectoryModel,
)
from app.db.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_cross_tenant_procedure_isolation_and_rejection(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User B cannot access, validate, approve, disable, or rollback User A's procedure."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="tenant_a_gov@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="tenant_b_gov@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])

    proc_a = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_a_id,
        task_domain="security",
        name="Confidential Security Procedure",
        description="Private strategy containing tenant A operational data",
        trigger_conditions=["sensitive_flow"],
        ordered_steps=[{"step": 1, "tool": "safe_tool", "token": "confidential_token_123"}],
        required_tools=["safe_tool"],
        constraints=["private"],
        success_criteria=["ok"],
        confidence=0.92,
        usage_count=4,
        success_count=4,
        failure_count=0,
        version=1,
        status="CANDIDATE",
        is_global=False,
        source_trajectory_ids=[str(uuid.uuid4()) for _ in range(4)],
        source_evaluation_ids=[str(uuid.uuid4()) for _ in range(4)],
        validation_score=0.90,
        safety_classification="HIGH",
        approval_status="NONE",
        provenance_metadata={"tenant": "A"},
    )
    db_session.add(proc_a)
    await db_session.commit()

    token_b = create_access_token(
        user_id=user_b_id,
        email="tenant_b_gov@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read", "task:write"],
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User B tries to GET User A's procedure details -> 404
    resp_get = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc_a.id}",
        headers=headers_b,
    )
    assert resp_get.status_code == 404

    # 2. User B tries to validate User A's procedure -> 404
    resp_val = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/validate",
        headers=headers_b,
    )
    assert resp_val.status_code == 404

    # 3. User B tries to request promotion for User A's procedure -> 404
    resp_req = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/request-promotion",
        headers=headers_b,
    )
    assert resp_req.status_code == 404

    # 4. User B tries to approve User A's procedure -> 404
    resp_app = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/approve",
        headers=headers_b,
        json={"decision": "APPROVED", "reason": "Illegitimate approval"},
    )
    assert resp_app.status_code == 404

    # 5. User B tries to promote User A's procedure -> 400 or 404
    resp_pro = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/promote",
        headers=headers_b,
    )
    assert resp_pro.status_code in (400, 404)

    # 6. User B tries to disable User A's procedure -> 404
    resp_dis = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/disable",
        headers=headers_b,
    )
    assert resp_dis.status_code == 404

    # 7. User B tries to rollback User A's procedure -> 400 or 404
    resp_rb = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/rollback",
        headers=headers_b,
        json={"reason": "Unauthorized rollback attempt"},
    )
    assert resp_rb.status_code in (400, 404)

    # 8. User B tries to check drift for User A's procedure -> 404
    resp_dr = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc_a.id}/drift",
        headers=headers_b,
    )
    assert resp_dr.status_code == 404


@pytest.mark.asyncio
async def test_high_risk_human_approval_lifecycle_and_promotion(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Full lifecycle: Candidate -> Gate Blocked (High Risk) -> Human Approval -> Promotion."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="operator_gov@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)

    proc = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_id,
        task_domain="financial_trade",
        name="High Value Automated Settlement",
        description="Strategy for clearing multi-currency settlements",
        trigger_conditions=["settlement_requested"],
        ordered_steps=[{"step": 1, "tool": "settlement_tool", "action": "execute"}],
        required_tools=["settlement_tool"],
        constraints=["regulatory_compliance"],
        success_criteria=["reconciled"],
        confidence=0.94,
        usage_count=5,
        success_count=5,
        failure_count=0,
        version=1,
        status="CANDIDATE",
        is_global=False,
        source_trajectory_ids=[str(uuid.uuid4()) for _ in range(5)],
        source_evaluation_ids=[str(uuid.uuid4()) for _ in range(5)],
        validation_score=0.91,
        safety_classification="HIGH",
        approval_status="NONE",
        provenance_metadata={},
    )
    db_session.add(proc)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="operator_gov@example.com",
        roles=["ADMIN", "SECURITY_OFFICER"],
        scopes=["task:read", "task:write"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: Request promotion -> Gate fails because HIGH risk requires human approval
    req_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/request-promotion",
        headers=headers,
    )
    assert req_resp.status_code == 200
    gate_data = req_resp.json()
    assert gate_data["passed"] is False
    assert gate_data["requires_human_approval"] is True
    assert gate_data["is_blocked_by_approval"] is True
    assert gate_data["status"] == "PENDING_APPROVAL"

    # Direct promote should fail
    fail_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/promote",
        headers=headers,
    )
    assert fail_resp.status_code == 400
    assert "rejected" in fail_resp.json()["detail"].lower()

    # Step 2: Explicit human approval by authorized operator
    appr_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/approve",
        headers=headers,
        json={"decision": "APPROVED", "reason": "Reviewed compliance & risk controls."},
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["decision"] == "APPROVED"

    # Step 3: Re-evaluate promotion gates -> now passes
    val_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/validate",
        headers=headers,
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["passed"] is True
    assert val_data["status"] == "PROMOTED"

    # Step 4: Finalize promotion into active production
    prom_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/promote",
        headers=headers,
    )
    assert prom_resp.status_code == 200
    prom_data = prom_resp.json()
    assert prom_data["status"] == "PROMOTED"
    assert prom_data["promoted_at"] is not None

    # Verify version snapshot was recorded in history
    hist_resp = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc.id}/history",
        headers=headers,
    )
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert len(hist_data) >= 1
    assert hist_data[0]["version"] == 1


@pytest.mark.asyncio
async def test_procedure_rollback_and_disable_preserves_provenance(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Disabling or rolling back a procedure updates status and preserves full history."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="rollback_gov@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)

    proc = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_id,
        task_domain="database",
        name="Query Optimization Strategy",
        description="v2 strategy that later exhibits regression",
        trigger_conditions=["sql_optimize"],
        ordered_steps=[{"step": 1, "tool": "db_tool", "action": "explain"}],
        required_tools=["db_tool"],
        constraints=[],
        success_criteria=[],
        confidence=0.85,
        usage_count=10,
        success_count=8,
        failure_count=2,
        version=2,
        status="PROMOTED",
        is_global=False,
        validation_score=0.88,
        safety_classification="LOW",
        approval_status="NONE",
    )
    db_session.add(proc)

    # Seed an earlier version 1 snapshot
    v1_snapshot = LearnedProcedureVersionModel(
        id=uuid.uuid4(),
        procedure_id=proc.id,
        user_id=user_id,
        version=1,
        status="PROMOTED",
        snapshot={
            "name": "Query Optimization Strategy v1",
            "description": "Known-good v1 strategy",
            "trigger_conditions": ["sql_optimize"],
            "ordered_steps": [{"step": 1, "tool": "db_tool", "action": "simple_query"}],
            "required_tools": ["db_tool"],
            "constraints": [],
            "success_criteria": [],
        },
        validation_score=0.92,
        confidence=0.90,
        safety_classification="LOW",
    )
    db_session.add(v1_snapshot)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="rollback_gov@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read", "task:write"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Execute rollback to version 1
    rb_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/rollback",
        headers=headers,
        json={"target_version": 1, "reason": "Detected latency regression in v2."},
    )
    assert rb_resp.status_code == 200
    rb_data = rb_resp.json()
    assert rb_data["rolled_back_from_version"] == 2
    assert rb_data["restored_to_version"] == 1
    assert rb_data["status"] == "ROLLED_BACK"

    # Verify procedure now reflects version 1 tactics
    get_resp = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc.id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    proc_detail = get_resp.json()
    assert proc_detail["name"] == "Query Optimization Strategy v1"
    assert proc_detail["ordered_steps"][0]["action"] == "simple_query"

    # Now disable the procedure
    dis_resp = await async_client.post(
        f"/api/v1/learning/governance/procedures/{proc.id}/disable?reason=Decommissioned",
        headers=headers,
    )
    assert dis_resp.status_code == 200
    assert dis_resp.json()["disabled"] is True

    # Ensure records were not deleted
    get_dis = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc.id}",
        headers=headers,
    )
    assert get_dis.status_code == 200
    assert get_dis.json()["status"] == "DISABLED"


@pytest.mark.asyncio
async def test_governance_drift_monitoring_and_shadow_eval(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Drift detection endpoint and shadow comparison against baseline."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="drift_gov@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)

    proc = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_id,
        task_domain="data_proc",
        name="Data Transformation Strategy",
        description="Pipeline strategy",
        trigger_conditions=["data_ingest"],
        ordered_steps=[{"step": 1, "tool": "etl_tool"}],
        required_tools=["etl_tool"],
        constraints=[],
        success_criteria=[],
        confidence=0.90,
        usage_count=10,
        success_count=10,
        failure_count=0,
        version=1,
        status="PROMOTED",
        is_global=False,
        validation_score=0.90,
        procedure_metadata={"baseline_latency_ms": 300.0},
    )
    db_session.add(proc)

    # Seed 5 trailing executions with high failure rate
    for _ in range(5):
        traj = TrajectoryModel(
            id=uuid.uuid4(),
            user_id=user_id,
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            goal="Data Ingestion",
            selected_tools=["etl_tool"],
            is_success=False,  # High failure
            duration_ms=900.0,
            failures=[{"error": "Memory limit exceeded"}],
            retries_count=2,
            evaluation_summary={"task_completion_quality": 0.40},
        )
        db_session.add(traj)

    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="drift_gov@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read", "task:write"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Query drift
    drift_resp = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc.id}/drift",
        headers=headers,
    )
    assert drift_resp.status_code == 200
    drift_data = drift_resp.json()
    assert drift_data["drift_status"] in ("DEGRADED", "CRITICAL")
    assert len(drift_data["detected_issues"]) > 0

    # Run shadow evaluation
    shadow_resp = await async_client.post(
        "/api/v1/learning/governance/evaluations/shadow",
        headers=headers,
        json={
            "candidate_procedure_id": str(proc.id),
            "baseline_procedure_id": None,
            "sample_limit": 5,
        },
    )
    assert shadow_resp.status_code == 200
    shadow_data = shadow_resp.json()
    assert shadow_data["candidate_procedure_id"] == str(proc.id)
    assert "validation_score" in shadow_data["candidate_metrics"]


@pytest.mark.asyncio
async def test_secret_sanitization_on_governance_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Security Invariant: Governance endpoints must sanitize tokens/passwords."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="sanit_gov@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)

    proc = LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_id,
        task_domain="secrets",
        name="Sensitive Tool Strategy",
        description="Execute with api_key=sk-ant-api03-SECRET-KEY-1234567890",
        trigger_conditions=["use_auth"],
        ordered_steps=[
            {
                "step": 1,
                "tool": "api_tool",
                "password": "super_secret_password_123",
                "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.secret",
            }
        ],
        required_tools=["api_tool"],
        constraints=[],
        success_criteria=[],
        confidence=0.88,
        usage_count=3,
        success_count=3,
        failure_count=0,
        version=1,
        status="PROMOTED",
        is_global=False,
        validation_score=0.88,
        provenance_metadata={"api_key": "sk-proj-CONFIDENTIAL_API_KEY_123"},
        procedure_metadata={"secret_token": "secret_12345"},
    )
    db_session.add(proc)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="sanit_gov@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    resp = await async_client.get(
        f"/api/v1/learning/governance/procedures/{proc.id}",
        headers=headers,
    )
    assert resp.status_code == 200
    content = resp.text
    assert "super_secret_password_123" not in content
    assert "sk-proj-CONFIDENTIAL_API_KEY_123" not in content
    assert "[REDACTED_SECRET]" in content




@pytest.mark.asyncio
async def test_governance_config_isolation_and_security_invariant(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Governance thresholds are strictly isolated per tenant, and procedures cannot bypass ABAC."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id, email="cfg_a@example.com", hashed_password="pw", is_active=True
    )
    user_b = User(
        id=user_b_id, email="cfg_b@example.com", hashed_password="pw", is_active=True
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    token_a = create_access_token(
        user_id=user_a_id,
        email="cfg_a@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read", "task:write"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    token_b = create_access_token(
        user_id=user_b_id,
        email="cfg_b@example.com",
        roles=["DEVELOPER"],
        scopes=["task:read", "task:write"],
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant A updates governance config to stricter thresholds
    put_resp = await async_client.put(
        "/api/v1/learning/governance/config",
        headers=headers_a,
        json={"min_success_rate": 0.95, "min_evaluation_count": 8},
    )
    assert put_resp.status_code == 200
    cfg_a = put_resp.json()
    assert cfg_a["min_success_rate"] == 0.95
    assert cfg_a["min_evaluation_count"] == 8

    # Tenant B queries governance config -> untouched defaults
    get_resp_b = await async_client.get(
        "/api/v1/learning/governance/config",
        headers=headers_b,
    )
    assert get_resp_b.status_code == 200
    cfg_b = get_resp_b.json()
    assert cfg_b["min_success_rate"] == 0.85
    assert cfg_b["min_evaluation_count"] == 3


