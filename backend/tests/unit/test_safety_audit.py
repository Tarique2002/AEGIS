"""Unit tests for SafetyAuditLogger and secret redaction."""

import uuid

import pytest
from app.safety.audit import SafetyAuditLogger, redact_secrets
from app.safety.schemas import RiskLevel, SafetyDecision, SafetyDecisionType


def test_secret_redaction_strings_and_dicts() -> None:
    raw_str = "Use Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_signature to connect"
    scrubbed = redact_secrets(raw_str)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed
    assert "[REDACTED_TOKEN]" in scrubbed

    raw_dict = {
        "api_key": "sk-1234567890abcdef1234567890",
        "nested": {"password": "SuperSecretPassword123!"},
    }
    scrubbed_dict = redact_secrets(raw_dict)
    assert scrubbed_dict["api_key"] == "[REDACTED]"
    assert scrubbed_dict["nested"]["password"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_safety_audit_logger_event_creation() -> None:
    decision = SafetyDecision(
        allowed=True,
        decision_type=SafetyDecisionType.ALLOW,
        risk_level=RiskLevel.LOW,
        reason="Action allowed by safety policy.",
    )
    user_id = uuid.uuid4()
    event = await SafetyAuditLogger.log_decision(
        decision=decision,
        user_id=user_id,
        action="calculate",
    )
    assert event.user_id == user_id
    assert event.action == "calculate"
    assert event.decision == SafetyDecisionType.ALLOW
