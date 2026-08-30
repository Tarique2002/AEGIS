"""Strongly typed schemas for the AEGIS Multi-Layer Memory Engine."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class MemoryType(str, Enum):
    """Classification of memory tier."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryStatus(str, Enum):
    """Lifecycle status of a memory record."""

    CREATED = "created"
    ACTIVE = "active"
    EXPIRED = "expired"
    DELETED = "deleted"


class MemoryRecord(AegisBaseSchema):
    """Unified memory record model representing a stored memory item."""

    memory_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    memory_type: MemoryType
    user_id: uuid.UUID
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    content: str = Field(..., min_length=1)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class MemoryCandidate(AegisBaseSchema):
    """Payload proposing a memory item for ingestion before policy validation."""

    content: str = Field(..., min_length=1)
    memory_type: MemoryType = Field(default=MemoryType.SEMANTIC)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int | None = None


class ProceduralMemoryRecord(AegisBaseSchema):
    """Blueprint representing an executable procedure or strategy."""

    procedure_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=5)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    user_id: uuid.UUID
    version: int = 1
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EpisodicMemoryRecord(AegisBaseSchema):
    """Experiential summary record of a completed agent run."""

    episode_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str
    summary: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    status: str = "completed"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemorySearchQuery(AegisBaseSchema):
    """Parameters for querying across memory tiers."""

    query_text: str = Field(..., min_length=1)
    user_id: uuid.UUID | None = None  # Always overwritten/derived from trusted context
    memory_types: list[MemoryType] | None = None
    limit: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    filters: dict[str, Any] = Field(default_factory=dict)


class MemorySearchResult(AegisBaseSchema):
    """Ranked memory search result."""

    record: MemoryRecord
    score: float = Field(..., ge=0.0, le=1.0)
    matched_by: str
    similarity_score: float = 0.0
    recency_score: float = 0.0
    importance_score: float = 0.0
