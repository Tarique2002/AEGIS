"""Unit tests for SafetyPolicy rules, SSRF validation, and path safety."""

import pytest
from app.safety.errors import SafetyPolicyViolationError
from app.safety.policies import SafetyPolicy
from app.safety.schemas import RiskCategory, RiskLevel


def test_safety_policy_denied_categories() -> None:
    policy = SafetyPolicy()
    with pytest.raises(SafetyPolicyViolationError, match="explicitly DENIED"):
        policy.validate_action_risk(
            risk_level=RiskLevel.CRITICAL,
            categories=[RiskCategory.DESTRUCTIVE],
        )


def test_safety_policy_ssrf_blocking() -> None:
    policy = SafetyPolicy()
    # Localhost blocked
    with pytest.raises(SafetyPolicyViolationError, match="blocked by SSRF"):
        policy.validate_url_safety("http://localhost:8080/admin")

    with pytest.raises(SafetyPolicyViolationError, match="blocked by SSRF"):
        policy.validate_url_safety("http://127.0.0.1:8000/api")

    # Cloud metadata blocked
    with pytest.raises(SafetyPolicyViolationError, match="blocked by SSRF"):
        policy.validate_url_safety("http://169.254.169.254/latest/meta-data")

    # Disallowed scheme
    with pytest.raises(SafetyPolicyViolationError, match="Disallowed URL scheme"):
        policy.validate_url_safety("file:///etc/passwd")


def test_safety_policy_path_safety() -> None:
    policy = SafetyPolicy()
    # Traversal blocked
    with pytest.raises(SafetyPolicyViolationError, match="Directory traversal"):
        policy.validate_path_safety("../../secret/passwords.txt")

    # Sensitive path blocked
    with pytest.raises(SafetyPolicyViolationError, match="sensitive system path"):
        policy.validate_path_safety("/etc/shadow")
