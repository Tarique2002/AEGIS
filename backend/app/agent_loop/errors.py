"""Domain-specific exceptions for the Controlled Autonomous Agent Loop subsystem."""

from app.core.errors import (
    AgentLoopError,
    AgentLoopNotFoundError,
    ApprovalRequiredError,
    BudgetExceededError,
    InvalidDecisionError,
    SafetyStopTriggeredError,
    StagnationDetectedError,
)

__all__ = [
    "AgentLoopError",
    "AgentLoopNotFoundError",
    "ApprovalRequiredError",
    "BudgetExceededError",
    "InvalidDecisionError",
    "SafetyStopTriggeredError",
    "StagnationDetectedError",
]
