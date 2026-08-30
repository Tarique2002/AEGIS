"""Common Pydantic schemas, mixins, and foundational enums."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class AegisBaseSchema(BaseModel):
    """Base schema with standard Pydantic configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        protected_namespaces=(),
    )


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RunType(str, Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    EVALUATION = "evaluation"
    LEARNING = "learning"


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(AegisBaseSchema):
    """Structured message in conversational or agent history."""

    role: ChatRole
    content: str
    name: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class TimestampedSchema(AegisBaseSchema):
    """Schema mixin providing timezone-aware timestamps."""

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
