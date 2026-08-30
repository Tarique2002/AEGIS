"""Unit tests for ReportGenerator."""

import uuid

import pytest
from app.compliance.reports import ReportGenerator
from app.db.models.user import User
from app.security.audit_chain import AuditChainManager
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_compliance_report_generation(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    user = User(
        id=tenant_id, email="report_gen_test@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    # Append audit events
    await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="TASK_CREATED",
        action="create_task",
        resource_type="task",
        resource_id="1",
        payload={"step": 1},
        session=db_session,
    )

    report = await ReportGenerator.generate_report(
        tenant_id=tenant_id,
        report_type="SOC2_HIPAA",
        created_by=tenant_id,
        session=db_session,
    )

    assert report.tenant_id == tenant_id
    assert report.verification_status == "VERIFIED"
    assert report.summary.audit_chain_valid is True
    assert len(report.controls) > 0
    assert report.report_hash is not None
    assert len(report.report_hash) == 64
