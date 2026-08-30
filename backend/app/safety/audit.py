"""Append-oriented Safety Audit Logger with comprehensive secret redaction."""

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.safety import SafetyAuditModel
from app.safety.schemas import SafetyAuditEvent, SafetyDecision

logger = get_logger("aegis.safety.audit")

# Secret redaction patterns
SECRET_PATTERNS = [
    (r"(bearer\s+)[a-zA-Z0-9_\-\.]{20,}", r"\1[REDACTED_TOKEN]"),
    (r"(api[_\-\s]?key[\"'\s:=]+)[a-zA-Z0-9_\-\.]{16,}", r"\1[REDACTED_API_KEY]"),
    (r"(password[\"'\s:=]+)[^\s\"',;&]+", r"\1[REDACTED_PASSWORD]"),
    (r"(secret[\"'\s:=]+)[^\s\"',;&]+", r"\1[REDACTED_SECRET]"),
    (r"(postgresql(?:\+asyncpg)?://[^:]+:)([^@]+)(@)", r"\1[REDACTED_DB_PW]\3"),
    (
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
    ),
]


def redact_secrets(data: Any) -> Any:
    """Recursively scrub credentials, tokens, passwords, and private keys from data structures."""
    if isinstance(data, str):
        cleaned = data
        for pattern, replacement in SECRET_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        return cleaned
    elif isinstance(data, dict):
        return {
            k: (
                "[REDACTED]"
                if any(s in k.lower() for s in ["password", "secret", "token", "api_key", "auth"])
                else redact_secrets(v)
            )
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    return data


class SafetyAuditLogger:
    """Persists sanitized, append-only safety audit records."""

    @staticmethod
    async def log_decision(
        decision: SafetyDecision,
        user_id: uuid.UUID,
        action: str,
        task_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        orchestration_id: uuid.UUID | None = None,
        worker_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> SafetyAuditEvent:
        """Create and persist an append-only safety audit record."""
        audit_event = SafetyAuditEvent(
            audit_id=uuid.uuid4(),
            user_id=user_id,
            task_id=task_id,
            run_id=run_id,
            orchestration_id=orchestration_id,
            worker_id=worker_id,
            action=action,
            decision=decision.decision_type,
            risk_level=decision.risk_level,
            gate=decision.gate_results[-1].gate_name if decision.gate_results else "SafetyGate",
            reason=decision.reason,
            policy_version=decision.policy_version,
            metadata=redact_secrets(decision.metadata),
        )

        logger.info(
            f"Safety Audit [{decision.decision_type.value}]: Action '{action}' by user "
            f"{user_id} - {decision.reason}"
        )

        if session:
            try:
                db_record = SafetyAuditModel(
                    id=audit_event.audit_id,
                    user_id=audit_event.user_id,
                    task_id=audit_event.task_id,
                    run_id=audit_event.run_id,
                    orchestration_id=audit_event.orchestration_id,
                    worker_id=audit_event.worker_id,
                    action=audit_event.action,
                    decision=audit_event.decision.value,
                    risk_level=audit_event.risk_level.value,
                    gate=audit_event.gate,
                    reason=audit_event.reason,
                    policy_version=audit_event.policy_version,
                    audit_metadata=audit_event.metadata,
                )
                session.add(db_record)
                await session.flush()
            except Exception as exc:
                logger.warning(f"Could not persist safety audit to DB: {exc}")

        return audit_event
