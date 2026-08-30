"""Unit tests for Cryptographic Audit Chain Manager."""

import uuid

import pytest
from app.db.models.user import User
from app.security.audit_chain import GENESIS_HASH, AuditChainManager
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_audit_chain_sequential_append(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    user = User(id=tenant_id, email="audit_chain_test@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()

    # Append Event 1
    event1 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type="TASK_CREATED",
        action="create_task",
        resource_type="task",
        resource_id="task-101",
        payload={"name": "Test Task 1"},
        session=db_session,
    )
    assert event1.sequence_number == 1
    assert event1.previous_hash == GENESIS_HASH
    assert len(event1.event_hash) == 64

    # Append Event 2
    event2 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type="TASK_COMPLETED",
        action="complete_task",
        resource_type="task",
        resource_id="task-101",
        payload={"name": "Test Task 1", "status": "completed"},
        session=db_session,
    )
    assert event2.sequence_number == 2
    assert event2.previous_hash == event1.event_hash
    assert event2.event_hash != event1.event_hash


def test_audit_secret_redaction_before_hashing() -> None:
    payload_with_secrets = {
        "user": "alice",
        "api_key": "sk-proj-supersecretkey12345",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy",
    }
    hash1 = AuditChainManager.compute_payload_hash(payload_with_secrets)

    payload_redacted = {
        "user": "alice",
        "api_key": "[REDACTED_API_KEY]",
        "authorization": "[REDACTED_BEARER_TOKEN]",
    }
    hash2 = AuditChainManager.compute_payload_hash(payload_redacted)

    assert hash1 == hash2
