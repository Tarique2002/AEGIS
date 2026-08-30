"""Unit tests for EvaluationPolicy, thresholds, and safety gate overrides."""

from app.evaluation.policies import EvaluationPolicy
from app.evaluation.schemas import FailureCategory


def test_policy_pass_threshold() -> None:
    policy = EvaluationPolicy(pass_threshold=0.70)

    # >= 0.70 passes
    passed, reason = policy.evaluate_pass_status(0.70, [FailureCategory.NONE])
    assert passed is True
    assert reason is None

    # < 0.70 fails
    passed, reason = policy.evaluate_pass_status(0.69, [FailureCategory.NONE])
    assert passed is False
    assert "did not meet pass threshold" in (reason or "")


def test_policy_critical_safety_override() -> None:
    policy = EvaluationPolicy(pass_threshold=0.70)

    # Score is very high (0.95), but critical policy violation occurred -> must FAIL
    passed, reason = policy.evaluate_pass_status(0.95, [FailureCategory.POLICY_VIOLATION])
    assert passed is False
    assert "critical failure category 'POLICY_VIOLATION'" in (reason or "")
    assert policy.is_passing(0.95, [FailureCategory.POLICY_VIOLATION]) is False


def test_policy_critical_timeout_override() -> None:
    policy = EvaluationPolicy(pass_threshold=0.70)

    passed, reason = policy.evaluate_pass_status(0.85, [FailureCategory.TIMEOUT])
    assert passed is False
    assert "TIMEOUT" in (reason or "")


def test_policy_non_critical_failure_category() -> None:
    policy = EvaluationPolicy(pass_threshold=0.70)

    # Resource inefficiency is non-critical on its own; passes if numerical score passes
    passed, reason = policy.evaluate_pass_status(0.75, [FailureCategory.RESOURCE_INEFFICIENCY])
    assert passed is True
