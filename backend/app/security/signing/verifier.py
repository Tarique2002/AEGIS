"""Audit Checkpoint Verifier verifying hash chains and cryptographic signatures."""

import uuid
from datetime import datetime

from app.core.logging import get_logger
from app.db.models.authorization import AuditChainModel
from app.db.models.compliance import AuditCheckpointModel
from app.schemas.common import utc_now
from app.security.audit_chain import AuditChainVerifier
from app.security.signing.base import SigningProvider
from app.security.signing.local import LocalSigningProvider
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("aegis.security.signing.verifier")


class CheckpointVerificationResult(BaseModel):
    """Result of audit checkpoint cryptographic verification."""

    valid: bool
    checkpoint_id: uuid.UUID
    tenant_id: uuid.UUID
    sequence_start: int
    sequence_end: int
    chain_head: str
    failure_reason: str | None = None
    signature_valid: bool = False
    chain_valid: bool = False
    verified_at: datetime = Field(default_factory=utc_now)


class AuditCheckpointVerifier:
    """Production verifier validating checkpoint signatures and underlying audit hash chains."""

    @staticmethod
    def construct_checkpoint_payload(
        tenant_id: uuid.UUID,
        sequence_start: int,
        sequence_end: int,
        chain_head: str,
    ) -> bytes:
        """Construct canonical bytes representation for checkpoint signature."""
        canonical_str = f"{tenant_id}:{sequence_start}:{sequence_end}:{chain_head}"
        return canonical_str.encode("utf-8")

    @classmethod
    async def verify_checkpoint(
        cls,
        checkpoint: AuditCheckpointModel,
        session: AsyncSession,
        provider: SigningProvider | None = None,
    ) -> CheckpointVerificationResult:
        """
        Full verification of an audit checkpoint:
        1. Verifies cryptographic signature using SigningProvider
        2. Validates underlying audit event records and sequence continuity in PostgreSQL
        3. Confirms that chain head matches the final event hash in sequence range
        """
        signing_provider = provider or LocalSigningProvider()

        # 1. Verify cryptographic signature
        payload_bytes = cls.construct_checkpoint_payload(
            tenant_id=checkpoint.tenant_id,
            sequence_start=checkpoint.sequence_start,
            sequence_end=checkpoint.sequence_end,
            chain_head=checkpoint.chain_head,
        )

        sig_valid = signing_provider.verify(payload_bytes, checkpoint.signature, checkpoint.key_id)

        if not sig_valid:
            logger.warning(
                f"Checkpoint {checkpoint.id} signature verification failed "
                f"for tenant {checkpoint.tenant_id}"
            )
            return CheckpointVerificationResult(
                valid=False,
                checkpoint_id=checkpoint.id,
                tenant_id=checkpoint.tenant_id,
                sequence_start=checkpoint.sequence_start,
                sequence_end=checkpoint.sequence_end,
                chain_head=checkpoint.chain_head,
                failure_reason="Invalid cryptographic signature on audit checkpoint.",
                signature_valid=False,
                chain_valid=False,
            )

        # 2. Query underlying audit events in range
        stmt = (
            select(AuditChainModel)
            .where(
                AuditChainModel.tenant_id == checkpoint.tenant_id,
                AuditChainModel.sequence_number >= checkpoint.sequence_start,
                AuditChainModel.sequence_number <= checkpoint.sequence_end,
            )
            .order_by(AuditChainModel.sequence_number.asc())
        )
        res = await session.execute(stmt)
        events = list(res.scalars().all())

        if not events:
            return CheckpointVerificationResult(
                valid=False,
                checkpoint_id=checkpoint.id,
                tenant_id=checkpoint.tenant_id,
                sequence_start=checkpoint.sequence_start,
                sequence_end=checkpoint.sequence_end,
                chain_head=checkpoint.chain_head,
                failure_reason="No audit events found within checkpoint sequence range.",
                signature_valid=True,
                chain_valid=False,
            )

        # Check sequence bounds
        if events[0].sequence_number != checkpoint.sequence_start:
            return CheckpointVerificationResult(
                valid=False,
                checkpoint_id=checkpoint.id,
                tenant_id=checkpoint.tenant_id,
                sequence_start=checkpoint.sequence_start,
                sequence_end=checkpoint.sequence_end,
                chain_head=checkpoint.chain_head,
                failure_reason=(
                    f"Sequence start mismatch: expected {checkpoint.sequence_start}, "
                    f"got {events[0].sequence_number}"
                ),
                signature_valid=True,
                chain_valid=False,
            )

        if events[-1].sequence_number != checkpoint.sequence_end:
            return CheckpointVerificationResult(
                valid=False,
                checkpoint_id=checkpoint.id,
                tenant_id=checkpoint.tenant_id,
                sequence_start=checkpoint.sequence_start,
                sequence_end=checkpoint.sequence_end,
                chain_head=checkpoint.chain_head,
                failure_reason=(
                    f"Sequence end mismatch: expected {checkpoint.sequence_end}, "
                    f"got {events[-1].sequence_number}"
                ),
                signature_valid=True,
                chain_valid=False,
            )

        # Confirm chain head matches final event hash
        if events[-1].event_hash != checkpoint.chain_head:
            return CheckpointVerificationResult(
                valid=False,
                checkpoint_id=checkpoint.id,
                tenant_id=checkpoint.tenant_id,
                sequence_start=checkpoint.sequence_start,
                sequence_end=checkpoint.sequence_end,
                chain_head=checkpoint.chain_head,
                failure_reason=(
                    f"Chain head mismatch: checkpoint specifies '{checkpoint.chain_head}', "
                    f"but event {events[-1].sequence_number} hash is '{events[-1].event_hash}'"
                ),
                signature_valid=True,
                chain_valid=False,
            )

        # 3. Verify overall chain continuity across the tenant
        full_chain_ver = await AuditChainVerifier.verify_tenant_chain(checkpoint.tenant_id, session)
        if not full_chain_ver.valid:
            return CheckpointVerificationResult(
                valid=False,
                checkpoint_id=checkpoint.id,
                tenant_id=checkpoint.tenant_id,
                sequence_start=checkpoint.sequence_start,
                sequence_end=checkpoint.sequence_end,
                chain_head=checkpoint.chain_head,
                failure_reason=f"Audit chain corruption detected: {full_chain_ver.failure_reason}",
                signature_valid=True,
                chain_valid=False,
            )

        return CheckpointVerificationResult(
            valid=True,
            checkpoint_id=checkpoint.id,
            tenant_id=checkpoint.tenant_id,
            sequence_start=checkpoint.sequence_start,
            sequence_end=checkpoint.sequence_end,
            chain_head=checkpoint.chain_head,
            failure_reason=None,
            signature_valid=True,
            chain_valid=True,
        )
