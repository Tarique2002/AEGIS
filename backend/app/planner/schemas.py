"""Strongly typed schemas for the AEGIS Dynamic Planner & Execution Graph (Phase 5)."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class PlanStatus(str, Enum):
    """Lifecycle status of an execution plan."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NodeType(str, Enum):
    """Supported typed graph execution node categories."""

    TOOL = "TOOL"
    LLM = "LLM"
    TRANSFORM = "TRANSFORM"
    CONDITION = "CONDITION"
    FINAL = "FINAL"


class NodeStatus(str, Enum):
    """Execution status of an individual graph node."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class TransformOperation(str, Enum):
    """Strict allowlist of permissible safe transform operations (no arbitrary code execution)."""

    SELECT_FIELD = "select_field"
    MERGE_VALUES = "merge_values"
    FORMAT_TEXT = "format_text"
    EXTRACT_VALUE = "extract_value"
    CONCATENATE = "concatenate"


class ConditionOperator(str, Enum):
    """Strict allowlist of permissible condition operators."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    EXISTS = "exists"
    IS_EMPTY = "is_empty"


class RetryPolicy(AegisBaseSchema):
    """Configurable retry policy for graph node execution."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    exponential_backoff: bool = Field(default=True)
    retryable_errors: list[str] = Field(default_factory=list)


class PlanNode(AegisBaseSchema):
    """Declarative specification of a single graph node in an execution plan."""

    node_id: str = Field(..., min_length=1, max_length=100)
    node_type: NodeType
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    dependencies: list[str] = Field(default_factory=list)
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map parameter names to upstream output keys or context variable paths",
    )
    output_key: str | None = Field(
        default=None,
        description="Key name used to publish node output into execution context",
    )
    configuration: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-specific configuration (e.g. tool_name, model, prompt, transform_op)",
    )
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    enabled: bool = Field(default=True)


class ExecutionPlan(AegisBaseSchema):
    """Structured execution plan composed of a validated DAG of PlanNodes."""

    plan_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str = Field(..., min_length=1)
    version: int = Field(default=1, ge=1)
    nodes: list[PlanNode] = Field(default_factory=list)
    status: PlanStatus = Field(default=PlanStatus.DRAFT)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ExecutionContext(AegisBaseSchema):
    """Runtime execution state and variable bag for an active execution graph pass."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    node_statuses: dict[str, NodeStatus] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    deadline: datetime | None = None


class ExecutionCheckpoint(AegisBaseSchema):
    """Snapshot of graph execution progress for durable checkpointing and resume."""

    checkpoint_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    plan_id: uuid.UUID
    task_id: uuid.UUID
    run_id: uuid.UUID
    completed_nodes: list[str] = Field(default_factory=list)
    node_states: dict[str, NodeStatus] = Field(default_factory=dict)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanNodeExecutionRecord(AegisBaseSchema):
    """Durable audit record of an individual node execution attempt."""

    node_execution_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    plan_id: uuid.UUID
    node_id: str
    status: NodeStatus
    attempt: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanCreateRequest(AegisBaseSchema):
    """Request to create and validate a structured execution plan."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str = Field(..., min_length=1)
    nodes: list[PlanNode] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteRequest(AegisBaseSchema):
    """Request to execute a validated execution plan."""

    variables: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = None


class PlanExecutionResponse(AegisBaseSchema):
    """Response returned upon graph execution completion or failure."""

    plan_id: uuid.UUID
    task_id: uuid.UUID
    run_id: uuid.UUID
    status: PlanStatus
    final_output: Any = None
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    skipped_nodes: list[str] = Field(default_factory=list)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    error: str | None = None


# ==============================================================================
# LLM Structured Output Schema for Plan Generation
# ==============================================================================


class LLMPlanOutput(AegisBaseSchema):
    """Structured plan generation contract produced by LLMPlanner."""

    objective: str
    nodes: list[PlanNode]
    reasoning: str | None = None
