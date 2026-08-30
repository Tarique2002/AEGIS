"""Unit tests for RetryHandler and exponential backoff calculations."""

from app.core.errors import AegisAuthorizationError, PlanValidationError
from app.planner.retry import RetryHandler
from app.planner.schemas import RetryPolicy
from app.tools.errors import ToolPolicyViolationError


def test_retryable_transient_error() -> None:
    policy = RetryPolicy(max_attempts=3, backoff_seconds=1.0)
    err = RuntimeError("Connection timeout to service")

    assert RetryHandler.is_retryable(err, attempt=1, retry_policy=policy) is True
    assert RetryHandler.is_retryable(err, attempt=2, retry_policy=policy) is True
    assert (
        RetryHandler.is_retryable(err, attempt=3, retry_policy=policy) is False
    )  # Max attempts reached


def test_non_retryable_policy_and_validation_errors() -> None:
    policy = RetryPolicy(max_attempts=3)

    policy_err = ToolPolicyViolationError("Tool rejected by security gate")
    assert RetryHandler.is_retryable(policy_err, attempt=1, retry_policy=policy) is False

    val_err = PlanValidationError("Schema invalid")
    assert RetryHandler.is_retryable(val_err, attempt=1, retry_policy=policy) is False

    auth_err = AegisAuthorizationError("Forbidden")
    assert RetryHandler.is_retryable(auth_err, attempt=1, retry_policy=policy) is False


def test_exponential_backoff_calculation() -> None:
    policy = RetryPolicy(backoff_seconds=2.0, exponential_backoff=True)

    # attempt 1 -> 2.0 * 2^0 = 2.0s
    assert RetryHandler.calculate_backoff_seconds(1, policy) == 2.0
    # attempt 2 -> 2.0 * 2^1 = 4.0s
    assert RetryHandler.calculate_backoff_seconds(2, policy) == 4.0
    # attempt 3 -> 2.0 * 2^2 = 8.0s
    assert RetryHandler.calculate_backoff_seconds(3, policy) == 8.0


def test_linear_backoff_calculation() -> None:
    policy = RetryPolicy(backoff_seconds=2.5, exponential_backoff=False)
    assert RetryHandler.calculate_backoff_seconds(1, policy) == 2.5
    assert RetryHandler.calculate_backoff_seconds(3, policy) == 2.5
