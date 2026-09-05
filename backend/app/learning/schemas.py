"""Strongly typed schemas for the AEGIS Self-Learning & Agent Evolution Engine (Phase 11)."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class LearningSignalType(str, Enum):
    """Categorization for structured learning signals derived from trajectories."""

    SUCCESSFUL_TOOL_SEQUENCE = "SUCCESSFUL_TOOL_SEQUENCE"
    FAILED_TOOL_SEQUENCE = "FAILED_TOOL_SEQUENCE"
    SUCCESSFUL_PLANNING_PATTERN = "SUCCESSFUL_PLANNING_PATTERN"
    FAILED_PLANNING_PATTERN = "FAILED_PLANNING_PATTERN"
    USEFUL_MEMORY_RETRIEVAL = "USEFUL_MEMORY_RETRIEVAL"
    USELESS_MEMORY_RETRIEVAL = "USELESS_MEMORY_RETRIEVAL"
    SUCCESSFUL_DELEGATION_PATTERN = "SUCCESSFUL_DELEGATION_PATTERN"
    FAILED_DELEGATION_PATTERN = "FAILED_DELEGATION_PATTERN"
    SUCCESSFUL_RECOVERY_STRATEGY = "SUCCESSFUL_RECOVERY_STRATEGY"
    RECURRING_FAILURE_MODE = "RECURRING_FAILURE_MODE"


class PromotionStatus(str, Enum):
    """Lifecycle status of a learned procedure."""

    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


class ExecutionTrajectory(AegisBaseSchema):
    """Authoritative structured capture of an agent task execution lifecycle."""

    trajectory_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    goal: str = Field(..., min_length=1)
    planning_steps: list[dict[str, Any]] = Field(default_factory=list)
    selected_tools: list[str] = Field(default_factory=list)
    tool_calls_metadata: list[dict[str, Any]] = Field(default_factory=list)
    worker_involvement: list[dict[str, Any]] = Field(default_factory=list)
    intermediate_decisions: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    retries_count: int = Field(default=0, ge=0)
    final_outcome: Any = None
    is_success: bool = True
    duration_ms: float = Field(default=0.0, ge=0.0)
    tokens_used: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    policy_decisions: list[dict[str, Any]] = Field(default_factory=list)
    evaluation_summary: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)


class TrajectoryCreate(AegisBaseSchema):
    """Input payload for capturing an execution trajectory."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    goal: str
    planning_steps: list[dict[str, Any]] = Field(default_factory=list)
    selected_tools: list[str] = Field(default_factory=list)
    tool_calls_metadata: list[dict[str, Any]] = Field(default_factory=list)
    worker_involvement: list[dict[str, Any]] = Field(default_factory=list)
    intermediate_decisions: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    retries_count: int = Field(default=0, ge=0)
    final_outcome: Any = None
    is_success: bool = True
    duration_ms: float = Field(default=0.0, ge=0.0)
    tokens_used: int | None = None
    cost_usd: float | None = None
    policy_decisions: list[dict[str, Any]] = Field(default_factory=list)
    evaluation_summary: dict[str, Any] | None = None


class OutcomeEvaluationResult(AegisBaseSchema):
    """Deterministic and multi-dimensional evaluation of a completed trajectory."""

    evaluation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    trajectory_id: uuid.UUID
    success: bool
    task_completion_quality: float = Field(..., ge=0.0, le=1.0)
    tool_effectiveness: float = Field(..., ge=0.0, le=1.0)
    execution_efficiency: float = Field(..., ge=0.0, le=1.0)
    unnecessary_steps: int = Field(default=0, ge=0)
    retry_frequency: int = Field(default=0, ge=0)
    failure_reasons: list[str] = Field(default_factory=list)
    policy_violations: int = Field(default=0, ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)


class LearningSignal(AegisBaseSchema):
    """Atomic distilled learning signal derived from a trajectory and outcome evaluation."""

    signal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    trajectory_id: uuid.UUID
    user_id: uuid.UUID
    signal_type: LearningSignalType
    domain: str = Field(default="general")
    context: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    discourages_strategy: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)


class LearnedProcedure(AegisBaseSchema):
    """Structured reusable strategy stored in procedural memory and PostgreSQL."""

    procedure_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    task_domain: str = Field(default="general")
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=5)
    trigger_conditions: list[str] = Field(default_factory=list)
    ordered_steps: list[dict[str, Any]] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    usage_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    version: int = Field(default=1, ge=1)
    status: PromotionStatus = Field(default=PromotionStatus.PROMOTED)
    is_global: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def historical_success_rate(self) -> float:
        """Laplace-smoothed success rate."""
        return (self.success_count + 1.0) / (self.usage_count + 2.0)


class ProcedureCandidate(AegisBaseSchema):
    """Unpromoted procedure proposal awaiting policy and safety validation."""

    candidate_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    trajectory_id: uuid.UUID
    user_id: uuid.UUID
    task_domain: str = Field(default="general")
    name: str
    description: str
    trigger_conditions: list[str] = Field(default_factory=list)
    ordered_steps: list[dict[str, Any]] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    validation_errors: list[str] = Field(default_factory=list)
    status: PromotionStatus = Field(default=PromotionStatus.CANDIDATE)
    created_at: datetime = Field(default_factory=utc_now)


class ProcedurePromotionDecision(AegisBaseSchema):
    """Auditable record of a promotion attempt for a candidate procedure."""

    audit_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    candidate_id: uuid.UUID
    procedure_id: uuid.UUID | None = None
    promoted: bool
    reason: str
    actor: str = "system"
    evaluation_score: float
    confidence: float
    validation_passed: bool
    version_transition: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class StrategyRecommendationQuery(AegisBaseSchema):
    """Request to find guidance strategies for a given task objective."""

    objective: str = Field(..., min_length=1)
    domain: str | None = None
    available_tools: list[str] | None = None
    limit: int = Field(default=3, ge=1, le=10)


class StrategyRecommendation(AegisBaseSchema):
    """Ranked procedural recommendation for agent execution."""

    procedure_id: uuid.UUID
    name: str
    description: str
    ordered_steps: list[dict[str, Any]]
    required_tools: list[str]
    match_score: float = Field(..., ge=0.0, le=1.0)
    success_rate: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    version: int
    rationale: str


class StrategyRecommendationResponse(AegisBaseSchema):
    """List of recommended procedures ranked by relevance, confidence, and success rate."""

    recommendations: list[StrategyRecommendation] = Field(default_factory=list)
    total_matches: int = 0


class LearningStatsResponse(AegisBaseSchema):
    """Summary metrics of the self-learning system for a tenant."""

    total_trajectories: int = 0
    successful_trajectories: int = 0
    failed_trajectories: int = 0
    total_signals: int = 0
    active_procedures: int = 0
    promoted_procedures: int = 0
    average_confidence: float = 0.0
