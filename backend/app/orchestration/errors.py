"""Domain exceptions for Phase 7 Multi-Agent Orchestration."""

from app.core.errors import (
    AggregationError,
    CircularDelegationError,
    DelegationPlanError,
    OrchestrationBudgetExceededError,
    OrchestrationError,
    OrchestrationNotFoundError,
    OrchestrationSafetyStopError,
    WorkerBlockedError,
    WorkerExecutionError,
    WorkerTimeoutError,
)

__all__ = [
    "AggregationError",
    "CircularDelegationError",
    "DelegationPlanError",
    "OrchestrationBudgetExceededError",
    "OrchestrationError",
    "OrchestrationNotFoundError",
    "OrchestrationSafetyStopError",
    "WorkerBlockedError",
    "WorkerExecutionError",
    "WorkerTimeoutError",
]
