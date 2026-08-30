"""Controlled Autonomous Agent Loop subsystem package."""

from app.agent_loop.budget import AgentBudget
from app.agent_loop.controller import AgentController, ApprovalProvider, DefaultApprovalProvider
from app.agent_loop.decision import DecisionEngine
from app.agent_loop.errors import (
    AgentLoopError,
    AgentLoopNotFoundError,
    ApprovalRequiredError,
    BudgetExceededError,
    InvalidDecisionError,
    SafetyStopTriggeredError,
    StagnationDetectedError,
)
from app.agent_loop.guardrails import AgentGuardrails, ProgressTracker
from app.agent_loop.iteration import AgentIterationRunner
from app.agent_loop.observation import ObservationBuilder
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.repository import AgentLoopRepository
from app.agent_loop.schemas import (
    AgentBudgetResponse,
    AgentBudgetState,
    AgentDecision,
    AgentIterationRecord,
    AgentIterationResponse,
    AgentLoopCreateRequest,
    AgentLoopResponse,
    AgentLoopResumeRequest,
    AgentLoopState,
    AgentLoopStatus,
    ApprovalRequest,
    ApprovalResult,
    AutonomyLevel,
    DecisionType,
)
from app.agent_loop.service import AgentLoopService

__all__ = [
    "AgentBudget",
    "AgentBudgetResponse",
    "AgentBudgetState",
    "AgentController",
    "AgentDecision",
    "AgentGuardrails",
    "AgentIterationRecord",
    "AgentIterationResponse",
    "AgentIterationRunner",
    "AgentLoopCreateRequest",
    "AgentLoopError",
    "AgentLoopNotFoundError",
    "AgentLoopPolicy",
    "AgentLoopRepository",
    "AgentLoopResponse",
    "AgentLoopResumeRequest",
    "AgentLoopService",
    "AgentLoopState",
    "AgentLoopStatus",
    "ApprovalProvider",
    "ApprovalRequest",
    "ApprovalRequiredError",
    "ApprovalResult",
    "AutonomyLevel",
    "BudgetExceededError",
    "DecisionEngine",
    "DecisionType",
    "DefaultApprovalProvider",
    "InvalidDecisionError",
    "ObservationBuilder",
    "ProgressTracker",
    "SafetyStopTriggeredError",
    "StagnationDetectedError",
]
