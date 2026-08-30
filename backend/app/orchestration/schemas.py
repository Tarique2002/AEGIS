"""Pydantic schemas and typed contracts for Multi-Agent Orchestration & Delegation."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.evaluation.schemas import EvaluationResult
from app.memory.schemas import MemoryType
from app.schemas.common import AegisBaseSchema, utc_now


class OrchestrationStatus(str, Enum):
    """Lifecycle states of a multi-agent orchestration session."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    DISPATCHING = "DISPATCHING"
    RUNNING = "RUNNING"
    AGGREGATING = "AGGREGATING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class WorkerType(str, Enum):
    """Standardized specialized agent worker roles."""

    GENERAL = "GENERAL"
    RESEARCH = "RESEARCH"
    ANALYSIS = "ANALYSIS"
    CODING = "CODING"
    DATA = "DATA"
    SYNTHESIS = "SYNTHESIS"


class DelegationExecutionMode(str, Enum):
    """Execution dispatch mode for delegated worker tasks."""

    SEQUENTIAL = "SEQUENTIAL"
    PARALLEL = "PARALLEL"
    DEPENDENCY_GRAPH = "DEPENDENCY_GRAPH"


class DelegatedTaskStatus(str, Enum):
    """Status of an individual delegated worker sub-task."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"


class ConflictResolutionMethod(str, Enum):
    """Resolution strategy when workers produce contradictory results."""

    EVIDENCE_PRIORITY = "EVIDENCE_PRIORITY"
    RE_EVALUATION = "RE_EVALUATION"
    ADDITIONAL_WORKER = "ADDITIONAL_WORKER"
    UNRESOLVED = "UNRESOLVED"


class WorkerDefinition(AegisBaseSchema):
    """Specification and permission boundary for a specialized worker agent."""

    worker_id: str = Field(default_factory=lambda: f"worker_{uuid.uuid4().hex[:8]}")
    worker_type: WorkerType = WorkerType.GENERAL
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_memory_types: list[MemoryType] = Field(default_factory=list)
    max_iterations: int = Field(default=5, ge=1, le=15)
    max_tool_calls: int = Field(default=10, ge=0, le=25)
    max_llm_calls: int = Field(default=8, ge=1, le=20)
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class DelegatedTask(AegisBaseSchema):
    """An individual bounded task delegated to a specialized worker."""

    delegated_task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    worker_id: str
    worker_type: WorkerType = WorkerType.GENERAL
    title: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    input_context: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = Field(default="Structured outcome")
    dependencies: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=10)
    status: DelegatedTaskStatus = DelegatedTaskStatus.PENDING
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    is_optional: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    error: str | None = None


class DelegationPlan(AegisBaseSchema):
    """Structured plan decomposing an orchestration objective into worker tasks."""

    plan_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    orchestration_id: uuid.UUID
    objective: str = Field(..., min_length=1)
    tasks: list[DelegatedTask] = Field(default_factory=list)
    execution_mode: DelegationExecutionMode = DelegationExecutionMode.DEPENDENCY_GRAPH
    max_parallel_workers: int = Field(default=3, ge=1, le=5)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(AegisBaseSchema):
    """Normalized structured result returned by an individual worker pass."""

    worker_id: str
    delegated_task_id: str
    worker_type: WorkerType = WorkerType.GENERAL
    status: DelegatedTaskStatus
    result: Any = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    execution_summary: str = Field(default="")
    evaluation: EvaluationResult | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConflictRecord(AegisBaseSchema):
    """Record of contradictory findings detected across worker results."""

    conflict_id: str = Field(default_factory=lambda: f"conflict_{uuid.uuid4().hex[:8]}")
    worker_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    severity: str = "MEDIUM"
    resolution_status: str = "UNRESOLVED"
    resolution_method: ConflictResolutionMethod = ConflictResolutionMethod.UNRESOLVED
    resolution_notes: str = ""


class AggregatedResult(AegisBaseSchema):
    """Synthesized outcome combining validated worker outputs."""

    orchestration_id: uuid.UUID
    status: OrchestrationStatus
    final_output: Any = None
    summary: str = Field(default="")
    worker_contributions: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evaluation: EvaluationResult | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class OrchestrationBudgetState(AegisBaseSchema):
    """Cumulative resource usage tracked across the entire orchestration session."""

    worker_count: int = 0
    active_workers: int = 0
    completed_workers: int = 0
    failed_workers: int = 0
    total_iterations: int = 0
    total_tool_calls: int = 0
    total_llm_calls: int = 0
    total_retries: int = 0
    rework_rounds: int = 0
    elapsed_time_ms: float = 0.0
    estimated_tokens: int = 0
    estimated_cost_usd: float = 0.0


class OrchestrationState(AegisBaseSchema):
    """Full in-memory and persisted state of a multi-agent orchestration session."""

    orchestration_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    objective: str
    status: OrchestrationStatus = OrchestrationStatus.CREATED
    delegation_plan: DelegationPlan | None = None
    worker_results: dict[str, WorkerResult] = Field(default_factory=dict)
    aggregated_result: AggregatedResult | None = None
    budget: OrchestrationBudgetState = Field(default_factory=OrchestrationBudgetState)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# API Request / Response Contracts
# ==============================================================================


class OrchestrationCreateRequest(AegisBaseSchema):
    """Request payload to initiate a controlled multi-agent orchestration."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str = Field(..., min_length=1)
    workers: list[WorkerDefinition] | None = None
    execution_mode: DelegationExecutionMode = DelegationExecutionMode.DEPENDENCY_GRAPH
    max_parallel_workers: int = Field(default=3, ge=1, le=5)
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationResumeRequest(AegisBaseSchema):
    """Request payload to resume an orchestration session from checkpoint."""

    rework_reason: str | None = None
    additional_workers: list[WorkerDefinition] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerStateResponse(AegisBaseSchema):
    """Detailed status of a worker task within orchestration."""

    delegated_task_id: str
    worker_id: str
    worker_type: WorkerType
    title: str
    status: DelegatedTaskStatus
    dependencies: list[str]
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class OrchestrationResponse(AegisBaseSchema):
    """High-level response payload for orchestration endpoints."""

    orchestration_id: uuid.UUID
    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str
    status: OrchestrationStatus
    plan_id: uuid.UUID | None = None
    tasks_count: int = 0
    completed_tasks_count: int = 0
    final_output: Any = None
    budget: OrchestrationBudgetState
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationBudgetResponse(AegisBaseSchema):
    """Orchestration-level budget and remaining allowances."""

    orchestration_id: uuid.UUID
    budget: OrchestrationBudgetState
    limits: dict[str, Any]
    remaining: dict[str, Any]
