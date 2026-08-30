"""Unit tests for EvidenceCollector."""

import uuid

import pytest
from app.compliance.evidence import EvidenceCollector
from app.db.models.user import User
from app.security.audit_chain import AuditChainManager
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_evidence_collection_from_real_events(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    user = User(
        id=tenant_id, email="evidence_test@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    # Append 2 real audit events
    await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="TASK_CREATED",
        action="create_task",
        resource_type="task",
        resource_id="1",
        payload={"name": "Evidence Test Task"},
        session=db_session,
    )

    evidence_records = await EvidenceCollector.collect_evidence_for_tenant(
        tenant_id=tenant_id,
        start_time=None,
        end_time=None,
        session=db_session,
    )

    assert len(evidence_records) >= 2
    control_ids = [e.control_id for e in evidence_records]
    assert "AUTH-001" in control_ids
    assert "AUD-002" in control_ids
