"""Retry policy evaluation, transient error classification, and backoff scheduling."""

from app.core.errors import (
    AegisAuthenticationError,
    AegisAuthorizationError,
    AegisValidationError,
    CyclicDependencyError,
    PlanValidationError,
)
from app.planner.schemas import RetryPolicy
from app.tools.errors import ToolPolicyViolationError, ToolValidationError


class RetryHandler:
    """
    Determines retry eligibility and calculates exponential backoff durations.
    Explicitly refuses to retry deterministic or policy-violating failures.
    """

    NON_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
        AegisValidationError,
        PlanValidationError,
        CyclicDependencyError,
        AegisAuthorizationError,
        AegisAuthenticationError,
        ToolPolicyViolationError,
        ToolValidationError,
    )

    @classmethod
    def is_retryable(
        cls,
        exc: Exception,
        attempt: int,
        retry_policy: RetryPolicy,
    ) -> bool:
        """
        Check if an error is eligible for retry under the specified policy.
        """
        if attempt >= retry_policy.max_attempts:
            return False

        if isinstance(exc, cls.NON_RETRYABLE_EXCEPTIONS):
            return False

        # If explicit retryable error substrings are configured, check match
        if retry_policy.retryable_errors:
            err_str = str(exc).lower()
            return any(r.lower() in err_str for r in retry_policy.retryable_errors)

        return True

    @classmethod
    def calculate_backoff_seconds(
        cls,
        attempt: int,
        retry_policy: RetryPolicy,
    ) -> float:
        """
        Compute bounded backoff sleep duration in seconds.
        """
        if not retry_policy.exponential_backoff:
            return max(0.0, min(60.0, retry_policy.backoff_seconds))

        factor = 2 ** max(0, attempt - 1)
        delay = float(retry_policy.backoff_seconds * factor)
        return max(0.0, min(60.0, delay))
