"""Unit tests for AuditChainVerifier tampering detection."""

import uuid

import pytest
from app.db.models.user import User
from app.security.audit_chain import (
    AuditChainManager,
    AuditChainVerifier,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_audit_chain_verifier_valid_chain(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    user = User(id=tenant_id, email="verifier_test@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    for i in range(3):
        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type="TEST_EVENT",
            action=f"action_{i}",
            resource_type="test_res",
            resource_id=f"res_{i}",
            payload={"index": i},
            session=db_session,
        )

    result = await AuditChainVerifier.verify_tenant_chain(tenant_id, db_session)
    assert result.valid is True
    assert result.checked_events == 3
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_audit_chain_verifier_detects_payload_tampering(
    db_session: AsyncSession,
) -> None:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    user = User(id=tenant_id, email="verifier_tamper@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    event1 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type="TEST_EVENT",
        action="action_1",
        resource_type="test_res",
        resource_id="res_1",
        payload={"amount": 100},
        session=db_session,
    )

    # Tamper with metadata payload directly in DB
    event1.audit_metadata = {"amount": 999999}
    await db_session.flush()

    result = await AuditChainVerifier.verify_tenant_chain(tenant_id, db_session)
    assert result.valid is False
    assert "Payload tampering detected" in (result.failure_reason or "")
