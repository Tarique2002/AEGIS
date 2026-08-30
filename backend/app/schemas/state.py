"""Strongly typed Agent State models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import (
    AegisBaseSchema,
    ChatMessage,
    RiskLevel,
    StepStatus,
    TaskStatus,
    TimestampedSchema,
    utc_now,
)
from app.schemas.lifecycle import validate_task_transition
from app.schemas.telemetry import TelemetryData


class PlanStep(AegisBaseSchema):
    """Atomic step within a structured agent plan."""

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order: int
    title: str
    description: str
    required_tools: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    expected_output: str | None = None
    status: StepStatus = StepStatus.PENDING
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Plan(AegisBaseSchema):
    """Structured plan composed of ordered steps."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    objective: str
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ToolInvocation(AegisBaseSchema):
    """Represents a scheduled or executing tool call."""

    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invocation_id: uuid.UUID | None = None
    step_id: str | None = None
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    status: str = "pending"
    requires_approval: bool = False
    approval_id: str | None = None


class ToolObservation(AegisBaseSchema):
    """Observation resulting from tool execution."""

    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    observation_id: uuid.UUID | None = None
    invocation_id: uuid.UUID | None = None
    tool_name: str
    success: bool
    status: str = "completed"
    output: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class TokenUsage(AegisBaseSchema):
    """Cumulative token consumption and financial cost metrics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class RetrievedMemoryItem(AegisBaseSchema):
    """Context item retrieved from memory layers."""

    memory_id: str
    memory_type: str  # working | episodic | semantic | procedural
    content: str
    relevance_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummary(AegisBaseSchema):
    """Summary of self-evaluation metrics."""

    task_success_score: float = 0.0
    tool_accuracy_score: float = 0.0
    critique: str | None = None
    evaluated_at: datetime = Field(default_factory=utc_now)


class AgentState(TimestampedSchema):
    """
    Strongly typed, immutable-friendly state passed through agent nodes
    and persisted as checkpoints.
    """

    task_id: uuid.UUID
    run_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    objective: str
    status: TaskStatus = TaskStatus.PENDING

    # Planning & Execution State
    current_plan: Plan | None = None
    current_step_id: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)

    # Conversation History
    messages: list[ChatMessage] = Field(default_factory=list)

    # Tool Invocations and Observations (future-compatible data structures)
    tool_calls: list[ToolInvocation] = Field(default_factory=list)
    observations: list[ToolObservation] = Field(default_factory=list)

    # Memory & Context (future-compatible data structures)
    retrieved_memories: list[RetrievedMemoryItem] = Field(default_factory=list)

    # Errors & Resiliency
    errors: list[str] = Field(default_factory=list)
    retry_count: int = 0
    retries_count: int = 0
    max_retries: int = 3

    # Evaluation & Output
    evaluation: EvaluationSummary | None = None
    final_result: str | None = None

    # Lifecycle Timestamps
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Telemetry
    telemetry: TelemetryData | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def transition_to(self, new_status: TaskStatus) -> None:
        """
        Explicitly transition agent state to a new lifecycle status.
        Validates the transition rules and updates relevant timestamps.
        """
        validate_task_transition(self.status, new_status)
        now = utc_now()
        self.status = new_status
        self.updated_at = now

        if new_status in {TaskStatus.RUNNING, TaskStatus.PLANNING, TaskStatus.EXECUTING}:
            if self.started_at is None:
                self.started_at = now
        elif new_status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            self.completed_at = now

    def record_tool_execution(
        self,
        invocation: ToolInvocation,
        observation: ToolObservation,
    ) -> None:
        """
        Record a completed/attempted tool invocation and its resulting observation in state.
        """
        self.tool_calls.append(invocation)
        self.observations.append(observation)
        self.updated_at = utc_now()

    def add_retrieved_memories(
        self,
        memory_results: list[Any],
    ) -> None:
        """
        Attach retrieved memory items to the current agent state context.
        """
        for item in memory_results:
            if isinstance(item, RetrievedMemoryItem):
                self.retrieved_memories.append(item)
            elif hasattr(item, "record"):
                # MemorySearchResult object
                self.retrieved_memories.append(
                    RetrievedMemoryItem(
                        memory_id=str(item.record.memory_id),
                        memory_type=item.record.memory_type.value
                        if hasattr(item.record.memory_type, "value")
                        else str(item.record.memory_type),
                        content=item.record.content,
                        relevance_score=getattr(item, "score", 0.0),
                        metadata=item.record.metadata,
                    )
                )
        self.updated_at = utc_now()
