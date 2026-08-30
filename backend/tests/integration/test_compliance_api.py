"""Integration tests for Compliance API (controls, report generation, exports, evidence)."""

import uuid

import pytest
from app.core.auth import create_access_token
from app.db.models.user import User
from app.security.audit_chain import AuditChainManager
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_compliance_api_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    user = User(
        id=user_id, email="compliance_api@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        user_id=user_id,
        email="compliance_api@example.com",
        roles=["SECURITY_ADMIN"],
        scopes=["compliance:read", "compliance:generate", "audit:read"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Append an audit event
    await AuditChainManager.append_event(
        tenant_id=user_id,
        user_id=user_id,
        event_type="TASK_CREATED",
        action="create_task",
        resource_type="task",
        resource_id="1",
        payload={"secret_key": "sensitive123"},
        session=db_session,
    )

    # 1. GET /api/v1/compliance/controls
    ctrl_resp = await async_client.get("/api/v1/compliance/controls", headers=headers)
    assert ctrl_resp.status_code == 200
    assert len(ctrl_resp.json()) >= 10

    # 2. POST /api/v1/compliance/report
    rep_resp = await async_client.post(
        "/api/v1/compliance/report",
        json={"report_type": "SOC2_HIPAA"},
        headers=headers,
    )
    assert rep_resp.status_code == 201
    rep_data = rep_resp.json()
    report_id = rep_data["report_id"]
    assert rep_data["verification_status"] == "VERIFIED"

    # 3. GET /api/v1/compliance/report/{id}/export/json
    export_resp = await async_client.get(
        f"/api/v1/compliance/report/{report_id}/export/json", headers=headers
    )
    assert export_resp.status_code == 200
    assert "sensitive123" not in export_resp.text

    # 4. GET /api/v1/compliance/audit-integrity
    integ_resp = await async_client.get("/api/v1/compliance/audit-integrity", headers=headers)
    assert integ_resp.status_code == 200
    assert integ_resp.json()["chain_valid"] is True
