"""Cryptographically attested append-only audit chain with SHA-256 integrity verification."""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from app.core.logging import get_logger
from app.db.models.authorization import AuditChainModel
from app.safety.audit import redact_secrets
from app.schemas.common import utc_now
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("aegis.security.audit_chain")

GENESIS_HASH = "0" * 64


class AuditVerificationResult(BaseModel):
    """Result of verifying cryptographic audit chain integrity."""

    valid: bool
    checked_events: int
    first_invalid_event: int | None = None
    failure_reason: str | None = None
    chain_head: str | None = None
    verified_at: datetime = Field(default_factory=utc_now)


class AuditChainManager:
    """Manages append-only cryptographic audit event recording for multi-tenant isolation."""

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
        """Compute deterministic SHA-256 hash of redacted canonical JSON payload."""
        scrubbed = redact_secrets(payload)
        canonical = json.dumps(scrubbed, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_event_hash(
        sequence_number: int,
        event_type: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        payload_hash: str,
        previous_hash: str,
        policy_version: str,
    ) -> str:
        """Compute SHA-256 cryptographic chain hash for an audit event."""
        chain_payload = {
            "sequence_number": sequence_number,
            "event_type": event_type,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload_hash": payload_hash,
            "previous_hash": previous_hash,
            "policy_version": policy_version,
        }
        canonical = json.dumps(chain_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    async def append_event(
        cls,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        event_type: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        payload: dict[str, Any],
        session: AsyncSession,
        policy_version: str = "1.0.0",
    ) -> AuditChainModel:
        """Append a cryptographically attested audit event to the tenant's chain."""
        # 1. Fetch latest event for tenant
        stmt = (
            select(AuditChainModel)
            .where(AuditChainModel.tenant_id == tenant_id)
            .order_by(desc(AuditChainModel.sequence_number))
            .limit(1)
        )
        res = await session.execute(stmt)
        latest = res.scalar_one_or_none()

        next_seq = (latest.sequence_number + 1) if latest else 1
        prev_hash = latest.event_hash if latest else GENESIS_HASH

        # 2. Compute payload and event hashes
        scrubbed_payload = redact_secrets(payload)
        p_hash = cls.compute_payload_hash(scrubbed_payload)
        e_hash = cls.compute_event_hash(
            sequence_number=next_seq,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_hash=p_hash,
            previous_hash=prev_hash,
            policy_version=policy_version,
        )

        record = AuditChainModel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            sequence_number=next_seq,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_hash=p_hash,
            previous_hash=prev_hash,
            event_hash=e_hash,
            policy_version=policy_version,
            timestamp=utc_now(),
            audit_metadata=scrubbed_payload,
        )
        session.add(record)
        await session.flush()
        return record


class AuditChainVerifier:
    """Verifies cryptographic chain integrity and detects tampering across audit logs."""

    @classmethod
    async def verify_tenant_chain(
        cls,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> AuditVerificationResult:
        """Verify the full audit chain for a specific tenant."""
        stmt = (
            select(AuditChainModel)
            .where(AuditChainModel.tenant_id == tenant_id)
            .order_by(AuditChainModel.sequence_number.asc())
        )
        res = await session.execute(stmt)
        events = list(res.scalars().all())

        if not events:
            return AuditVerificationResult(
                valid=True,
                checked_events=0,
                chain_head=GENESIS_HASH,
            )

        expected_prev_hash = GENESIS_HASH
        for idx, event in enumerate(events, start=1):
            # Check sequence continuity
            if event.sequence_number != idx:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx,
                    first_invalid_event=event.sequence_number,
                    failure_reason=(
                        f"Sequence gap or reordering detected at event {event.id}: "
                        f"expected {idx}, got {event.sequence_number}"
                    ),
                    chain_head=expected_prev_hash,
                )

            # Check previous hash link
            if event.previous_hash != expected_prev_hash:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx,
                    first_invalid_event=event.sequence_number,
                    failure_reason=(
                        f"Broken chain link at sequence {event.sequence_number}: "
                        f"expected previous_hash '{expected_prev_hash}', "
                        f"got '{event.previous_hash}'"
                    ),
                    chain_head=expected_prev_hash,
                )

            # Recompute and verify payload hash
            actual_payload_hash = AuditChainManager.compute_payload_hash(event.audit_metadata)
            if event.payload_hash != actual_payload_hash:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx,
                    first_invalid_event=event.sequence_number,
                    failure_reason=(
                        f"Payload tampering detected at sequence {event.sequence_number}: "
                        f"recorded hash '{event.payload_hash}' != actual '{actual_payload_hash}'"
                    ),
                    chain_head=expected_prev_hash,
                )

            # Recompute and verify event hash
            recomputed_event_hash = AuditChainManager.compute_event_hash(
                sequence_number=event.sequence_number,
                event_type=event.event_type,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                payload_hash=event.payload_hash,
                previous_hash=event.previous_hash,
                policy_version=event.policy_version,
            )
            if event.event_hash != recomputed_event_hash:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx,
                    first_invalid_event=event.sequence_number,
                    failure_reason=(
                        f"Event hash tampering detected at sequence {event.sequence_number}: "
                        f"recorded '{event.event_hash}' != calculated '{recomputed_event_hash}'"
                    ),
                    chain_head=expected_prev_hash,
                )

            expected_prev_hash = event.event_hash

        return AuditVerificationResult(
            valid=True,
            checked_events=len(events),
            chain_head=expected_prev_hash,
        )
