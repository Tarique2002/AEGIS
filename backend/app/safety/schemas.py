"""Strongly typed schemas and contracts for the AEGIS Safety & Risk-Control Engine."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class RiskLevel(str, Enum):
    """Categorization of operational risk and potential blast radius."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    """Functional taxonomy of risk domains for consequential agent operations."""

    READ_ONLY = "READ_ONLY"
    COMPUTATION = "COMPUTATION"
    DATA_ACCESS = "DATA_ACCESS"
    MEMORY_WRITE = "MEMORY_WRITE"
    EXTERNAL_COMMUNICATION = "EXTERNAL_COMMUNICATION"
    CODE_EXECUTION = "CODE_EXECUTION"
    SYSTEM_OPERATION = "SYSTEM_OPERATION"
    FINANCIAL = "FINANCIAL"
    AUTHENTICATION = "AUTHENTICATION"
    PRIVACY = "PRIVACY"
    SECURITY = "SECURITY"
    DESTRUCTIVE = "DESTRUCTIVE"
    UNKNOWN = "UNKNOWN"


class SafetyDecisionType(str, Enum):
    """Authoritative outcome produced by safety gate evaluation."""

    ALLOW = "ALLOW"
    ALLOW_WITH_CONSTRAINTS = "ALLOW_WITH_CONSTRAINTS"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
    SAFETY_STOP = "SAFETY_STOP"


class ApprovalStatus(str, Enum):
    """Lifecycle status of a human-in-the-loop approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class InputTrustLevel(str, Enum):
    """Trust hierarchy preventing prompt injection and privilege escalation."""

    SYSTEM = "SYSTEM"
    AUTHENTICATED_USER = "AUTHENTICATED_USER"
    TRUSTED_INTERNAL = "TRUSTED_INTERNAL"
    WORKER_OUTPUT = "WORKER_OUTPUT"
    MEMORY = "MEMORY"
    TOOL_OUTPUT = "TOOL_OUTPUT"
    EXTERNAL_CONTENT = "EXTERNAL_CONTENT"
    UNKNOWN = "UNKNOWN"


class CircuitState(str, Enum):
    """Circuit breaker operational state."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class SafetyContext(AegisBaseSchema):
    """
    Execution context evaluated by Safety Gates.
    Strictly forbids storing raw credentials or secrets.
    """

    user_id: uuid.UUID
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    orchestration_id: uuid.UUID | None = None
    worker_id: str | None = None
    tool_name: str | None = None
    action: str
    arguments_metadata: dict[str, Any] = Field(default_factory=dict)
    requested_capabilities: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    environment: str = "development"
    budget_remaining: dict[str, Any] = Field(default_factory=dict)
    authenticated: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskAssessment(AegisBaseSchema):
    """Comprehensive risk evaluation result produced by RiskAssessmentEngine."""

    level: RiskLevel
    categories: list[RiskCategory] = Field(default_factory=list)
    factors: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explanation: str


class GateResult(AegisBaseSchema):
    """Result of an individual safety gate stage."""

    passed: bool
    gate_name: str
    reason: str
    decision: SafetyDecisionType
    risk_level: RiskLevel
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyDecision(AegisBaseSchema):
    """Final, aggregated safety verdict for a requested action."""

    decision_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    allowed: bool
    decision_type: SafetyDecisionType
    risk_level: RiskLevel
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    reason: str
    required_approval: bool = False
    policy_version: str = "1.0.0"
    evaluated_at: datetime = Field(default_factory=utc_now)
    evaluator: str = "SafetyGate"
    gate_results: list[GateResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalCreateRequest(AegisBaseSchema):
    """Request payload to initiate a human approval workflow."""

    task_id: uuid.UUID | None = None
    action: str
    resource: str
    risk_level: RiskLevel = RiskLevel.HIGH
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalResponse(AegisBaseSchema):
    """Structured response representing an approval request status."""

    approval_id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None = None
    action: str
    resource: str
    risk_level: RiskLevel
    reason: str
    status: ApprovalStatus
    policy_version: str
    requested_at: datetime
    expires_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenSession(AegisBaseSchema):
    """Security model representing an active or revoked token session."""

    token_id: str
    user_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    auth_scheme: str = "bearer"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyBudget(AegisBaseSchema):
    """Safety-tier cumulative resource and blast-radius tracking."""

    requests: int = 0
    tool_calls: int = 0
    external_calls: int = 0
    memory_writes: int = 0
    orchestration_starts: int = 0
    high_risk_actions: int = 0
    elapsed_time_ms: float = 0.0
    estimated_cost: float = 0.0


class SafetyAuditEvent(AegisBaseSchema):
    """Append-oriented safety audit record."""

    audit_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    user_id: uuid.UUID
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    orchestration_id: uuid.UUID | None = None
    worker_id: str | None = None
    action: str
    decision: SafetyDecisionType
    risk_level: RiskLevel
    gate: str
    reason: str
    policy_version: str = "1.0.0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RateLimitResult(AegisBaseSchema):
    """Outcome of a tenant or action rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    retry_after_seconds: int = 0
