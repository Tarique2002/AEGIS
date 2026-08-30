"""Strongly typed tool definition, invocation, observation, and telemetry schemas."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, RiskLevel, utc_now


class ToolPolicyClassification(str, Enum):
    """Explicit security policy classification for tool permissions."""

    SAFE = "SAFE"
    RESTRICTED = "RESTRICTED"
    DANGEROUS = "DANGEROUS"


class InvocationStatus(str, Enum):
    """Lifecycle statuses for a tool invocation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REJECTED = "rejected"


class ToolDefinition(AegisBaseSchema):
    """
    Deterministic, inspectable declaration of a tool's capabilities, schemas, and policy tier.
    """

    name: str = Field(..., min_length=1, max_length=100, description="Tool identifier")
    description: str = Field(..., min_length=5, description="Clear purpose of the tool")
    version: str = Field(default="1.0.0", description="Semantic version of tool")
    input_schema: dict[str, Any] = Field(..., description="JSON Schema for input parameters")
    output_schema: dict[str, Any] | None = Field(default=None, description="Output format schema")
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0, description="Timeout seconds")

    enabled: bool = Field(default=True, description="Whether the tool is available")
    policy_level: ToolPolicyClassification = Field(
        default=ToolPolicyClassification.SAFE, description="Security policy tier"
    )
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Operational risk metadata")
    capabilities: list[str] = Field(default_factory=list, description="Categorized capability tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary tool metadata")


class ToolInvocation(AegisBaseSchema):
    """
    Strongly typed tool execution request associated with an agent task/run.
    """

    invocation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tool_name: str = Field(..., min_length=1, description="Target tool name to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Input parameters for tool")
    task_id: uuid.UUID | None = Field(default=None, description="Associated agent task UUID")
    run_id: uuid.UUID | None = Field(default=None, description="Associated agent run UUID")
    timestamp: datetime = Field(default_factory=utc_now)
    status: InvocationStatus = Field(default=InvocationStatus.PENDING)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolObservation(AegisBaseSchema):
    """
    Structured outcome of a tool execution containing either output data or safe error information.
    """

    observation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    invocation_id: uuid.UUID = Field(..., description="Correlating invocation UUID")
    tool_name: str
    status: InvocationStatus
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class ToolTelemetry(AegisBaseSchema):
    """
    Telemetry recording resource consumption, sizes, and latency for a tool call.
    Only captures real metrics.
    """

    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: float | None = None
    tool_name: str
    tool_version: str
    status: InvocationStatus
    input_size_bytes: int | None = None
    output_size_bytes: int | None = None
