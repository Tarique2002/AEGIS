"""Task API Schemas for request and response serialization."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import (
    AegisBaseSchema,
    StepStatus,
    TaskStatus,
    TimestampedSchema,
)
from app.schemas.telemetry import TelemetryData


class TaskStepRead(TimestampedSchema):
    """Schema for returning task step details."""

    id: uuid.UUID
    task_id: uuid.UUID
    step_order: int
    title: str
    description: str
    status: StepStatus
    required_tools: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    expected_output: str | None = None
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentRunRead(TimestampedSchema):
    """Schema for returning agent run details."""

    id: uuid.UUID
    task_id: uuid.UUID
    run_type: str
    model_used: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    status: str
    result: str | None = None
    error: str | None = None
    started_at: datetime
    ended_at: datetime | None = None


class TaskCreate(AegisBaseSchema):
    """Payload for creating a new agent task."""

    objective: str = Field(..., min_length=3, description="Task objective or query to accomplish")
    user_id: uuid.UUID | None = Field(default=None, description="Optional associated user UUID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom task metadata")


class TaskRead(TimestampedSchema):
    """Schema for returning task details."""

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    objective: str
    status: TaskStatus
    result: str | None = None
    task_metadata: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime | None = None
    steps: list[TaskStepRead] = Field(default_factory=list)
    runs: list[AgentRunRead] = Field(default_factory=list)


class TaskExecutionResponse(AegisBaseSchema):
    """Response returned after submitting and executing a foundational agent task."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    status: TaskStatus
    objective: str
    result: str | None = None
    telemetry: TelemetryData | None = None
    created_at: datetime
    completed_at: datetime | None = None
