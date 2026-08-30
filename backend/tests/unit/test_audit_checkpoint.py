"""Unit tests for Audit Checkpoint creation and verification."""

import uuid

import pytest
from app.db.models.compliance import AuditCheckpointModel
from app.db.models.user import User
from app.schemas.common import utc_now
from app.security.audit_chain import AuditChainManager
from app.security.signing.local import LocalSigningProvider
from app.security.signing.verifier import AuditCheckpointVerifier
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_audit_checkpoint_verification_valid(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    user = User(
        id=tenant_id, email="checkpoint_test@example.com", hashed_password="pw", is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    # Append 3 events
    e1 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="EVT_1",
        action="act_1",
        resource_type="res",
        resource_id="1",
        payload={"step": 1},
        session=db_session,
    )
    e2 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="EVT_2",
        action="act_2",
        resource_type="res",
        resource_id="2",
        payload={"step": 2},
        session=db_session,
    )

    # Sign checkpoint over sequence 1 to 2
    signer = LocalSigningProvider()
    payload_bytes = AuditCheckpointVerifier.construct_checkpoint_payload(
        tenant_id, e1.sequence_number, e2.sequence_number, e2.event_hash
    )
    sig, key_id = signer.sign(payload_bytes)

    cp = AuditCheckpointModel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        sequence_start=e1.sequence_number,
        sequence_end=e2.sequence_number,
        chain_head=e2.event_hash,
        algorithm=signer.algorithm,
        key_id=key_id,
        signature=sig,
        signer_provider=signer.provider_type,
        verification_status="VALID",
        generated_at=utc_now(),
        checkpoint_metadata={},
    )
    db_session.add(cp)
    await db_session.commit()

    # Verify
    result = await AuditCheckpointVerifier.verify_checkpoint(cp, db_session, signer)
    assert result.valid is True
    assert result.signature_valid is True
    assert result.chain_valid is True


@pytest.mark.asyncio
async def test_audit_checkpoint_tampered_signature(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    user = User(id=tenant_id, email="tamper_cp@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()

    e1 = await AuditChainManager.append_event(
        tenant_id=tenant_id,
        user_id=tenant_id,
        event_type="EVT_1",
        action="act_1",
        resource_type="res",
        resource_id="1",
        payload={"step": 1},
        session=db_session,
    )

    signer = LocalSigningProvider()
    cp = AuditCheckpointModel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        sequence_start=e1.sequence_number,
        sequence_end=e1.sequence_number,
        chain_head=e1.event_hash,
        algorithm=signer.algorithm,
        key_id=signer.key_id,
        signature="invalid_tampered_signature_hex",
        signer_provider=signer.provider_type,
        verification_status="VALID",
        generated_at=utc_now(),
        checkpoint_metadata={},
    )
    db_session.add(cp)
    await db_session.commit()

    result = await AuditCheckpointVerifier.verify_checkpoint(cp, db_session, signer)
    assert result.valid is False
    assert result.signature_valid is False
