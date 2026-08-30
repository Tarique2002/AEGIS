"""Strongly typed schemas and models for the Controlled Autonomous Agent Loop subsystem."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.evaluation.schemas import EvaluationResult, ReflectionRecord
from app.planner.schemas import ExecutionPlan, PlanExecutionResponse
from app.schemas.common import AegisBaseSchema, utc_now


class AgentLoopStatus(str, Enum):
    """Lifecycle statuses for an autonomous agent loop."""

    CREATED = "CREATED"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    EVALUATING = "EVALUATING"
    REFLECTING = "REFLECTING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class DecisionType(str, Enum):
    """Action decisions produced at the end of an agent loop iteration."""

    CONTINUE = "CONTINUE"
    COMPLETE = "COMPLETE"
    REPLAN = "REPLAN"
    RETRY = "RETRY"
    WAIT = "WAIT"
    FAIL = "FAIL"
    SAFETY_STOP = "SAFETY_STOP"


class AutonomyLevel(str, Enum):
    """Configurable autonomy governance level."""

    SUPERVISED = "SUPERVISED"
    BOUNDED = "BOUNDED"
    AUTONOMOUS = "AUTONOMOUS"


class AgentBudgetState(AegisBaseSchema):
    """Cumulative resource consumption and budget tracking for an agent loop."""

    iterations: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    memory_reads: int = Field(default=0, ge=0)
    memory_writes: int = Field(default=0, ge=0)
    plan_executions: int = Field(default=0, ge=0)
    elapsed_time_ms: float = Field(default=0.0, ge=0.0)
    estimated_tokens: int = Field(default=0, ge=0)


class AgentObservation(AegisBaseSchema):
    """Structured, sanitized snapshot of the agent's environment and previous progress."""

    observation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    iteration_number: int = Field(..., ge=1)
    task_state: dict[str, Any] = Field(default_factory=dict)
    latest_plan: ExecutionPlan | None = None
    execution_results: PlanExecutionResponse | None = None
    evaluation_result: EvaluationResult | None = None
    reflection: ReflectionRecord | None = None
    relevant_memory: list[dict[str, Any]] = Field(default_factory=list)
    active_errors: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    remaining_budget: dict[str, Any] = Field(default_factory=dict)
    previous_failures: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)


class AgentDecision(AegisBaseSchema):
    """Structured decision output deciding next iteration action or termination."""

    decision_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    iteration_number: int = Field(..., ge=1)
    decision_type: DecisionType
    rationale: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    next_plan_required: bool = False
    stop_reason: str | None = None
    selected_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class LLMDecisionOutput(AegisBaseSchema):
    """Strict schema for LLM-proposed decisions."""

    decision_type: DecisionType
    rationale: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    next_plan_required: bool = False
    stop_reason: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)


class AgentIterationRecord(AegisBaseSchema):
    """Durable audit record of a single completed loop iteration."""

    iteration_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    loop_id: uuid.UUID
    iteration_number: int = Field(..., ge=1)
    status: AgentLoopStatus
    observation: AgentObservation | None = None
    decision: AgentDecision | None = None
    plan_id: uuid.UUID | None = None
    evaluation_id: uuid.UUID | None = None
    reflection_id: uuid.UUID | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentLoopState(AegisBaseSchema):
    """Full in-memory and persisted state of a controlled autonomous agent loop."""

    loop_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    objective: str
    autonomy_level: AutonomyLevel = AutonomyLevel.BOUNDED
    iteration_number: int = Field(default=0, ge=0)
    status: AgentLoopStatus = AgentLoopStatus.CREATED
    current_plan_id: uuid.UUID | None = None
    completed_iterations: list[AgentIterationRecord] = Field(default_factory=list)
    observations: list[AgentObservation] = Field(default_factory=list)
    decisions: list[AgentDecision] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    final_result: Any = None
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    budget: AgentBudgetState = Field(default_factory=AgentBudgetState)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(AegisBaseSchema):
    """Approval payload for human-in-the-loop governance hooks."""

    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    loop_id: uuid.UUID
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalResult(AegisBaseSchema):
    """Resolution of an approval request."""

    request_id: uuid.UUID
    approved: bool
    reviewer: str = "system"
    comments: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class AgentLoopCreateRequest(AegisBaseSchema):
    """Request payload to initiate a controlled autonomous agent loop."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str = Field(..., min_length=3, max_length=2000)
    autonomy_level: AutonomyLevel = AutonomyLevel.BOUNDED
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentLoopResumeRequest(AegisBaseSchema):
    """Request payload to resume an interrupted loop."""

    override_budget: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentLoopResponse(AegisBaseSchema):
    """Response payload returning loop status, budget, and outcomes."""

    loop_id: uuid.UUID
    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str
    iteration_number: int
    status: AgentLoopStatus
    current_plan_id: uuid.UUID | None = None
    final_result: Any = None
    budget: AgentBudgetState
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentIterationResponse(AegisBaseSchema):
    """Response summary of a single iteration."""

    iteration_id: uuid.UUID
    loop_id: uuid.UUID
    iteration_number: int
    status: AgentLoopStatus
    plan_id: uuid.UUID | None = None
    evaluation_id: uuid.UUID | None = None
    reflection_id: uuid.UUID | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class AgentBudgetResponse(AegisBaseSchema):
    """Response payload reporting resource budget and consumption."""

    loop_id: uuid.UUID
    budget: AgentBudgetState
    limits: dict[str, Any]
    remaining: dict[str, Any]
