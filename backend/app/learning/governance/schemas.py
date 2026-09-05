"""Pydantic schemas and enums for Phase 12 Production Learning Governance."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class SafetyClassification(str, Enum):
    """Risk and safety tier assigned to a learned procedure."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GovernanceProcedureStatus(str, Enum):
    """Authoritative lifecycle status for governed learned procedures."""

    CANDIDATE = "CANDIDATE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    DISABLED = "DISABLED"
    ROLLED_BACK = "ROLLED_BACK"
    DEPRECATED = "DEPRECATED"


class ApprovalStatus(str, Enum):
    """Human approval state for high-risk procedure promotion."""

    NONE = "NONE"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DriftStatus(str, Enum):
    """Evaluation drift status comparing recent performance to baseline."""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class GovernanceConfig(AegisBaseSchema):
    """Tenant-level configurable promotion gates and drift thresholds."""

    min_evaluation_count: int = Field(default=3, ge=1)
    min_success_rate: float = Field(default=0.85, ge=0.0, le=1.0)
    min_quality_score: float = Field(default=0.80, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    max_regression_tolerance: float = Field(default=0.05, ge=0.0, le=0.50)
    require_human_approval_for_high_risk: bool = Field(default=True)
    drift_evaluation_window: int = Field(default=20, ge=5, le=100)
    drift_warning_threshold: float = Field(default=0.10, ge=0.01, le=0.50)
    drift_critical_threshold: float = Field(default=0.20, ge=0.05, le=0.90)
    config_metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceConfigUpdate(AegisBaseSchema):
    """Optional payload for updating tenant governance configuration."""

    min_evaluation_count: int | None = Field(default=None, ge=1)
    min_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    max_regression_tolerance: float | None = Field(default=None, ge=0.0, le=0.50)
    require_human_approval_for_high_risk: bool | None = None
    drift_evaluation_window: int | None = Field(default=None, ge=5, le=100)
    drift_warning_threshold: float | None = Field(default=None, ge=0.01, le=0.50)
    drift_critical_threshold: float | None = Field(default=None, ge=0.05, le=0.90)
    config_metadata: dict[str, Any] | None = None


class GateCheckResult(AegisBaseSchema):
    """Single gate rule evaluation outcome."""

    rule_name: str
    passed: bool
    actual_value: Any
    expected_threshold: Any
    detail: str


class PromotionGateResult(AegisBaseSchema):
    """Comprehensive evaluation against all deterministic promotion gates."""

    passed: bool
    status: GovernanceProcedureStatus
    checks: list[GateCheckResult] = Field(default_factory=list)
    reason: str
    requires_human_approval: bool = False
    is_blocked_by_approval: bool = False


class DriftReport(AegisBaseSchema):
    """Real-time drift detection assessment comparing recent performance to baseline."""

    procedure_id: uuid.UUID
    procedure_name: str
    version: int
    drift_status: DriftStatus
    sample_size: int
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    recent_metrics: dict[str, float] = Field(default_factory=dict)
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    detected_issues: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utc_now)


class ShadowEvaluationRequest(AegisBaseSchema):
    """Request to evaluate candidate strategy against a baseline using historical runs."""

    candidate_procedure_id: uuid.UUID
    baseline_procedure_id: uuid.UUID | None = None
    sample_limit: int = Field(default=10, ge=1, le=50)


class ShadowEvaluationResult(AegisBaseSchema):
    """Deterministic comparative evaluation of candidate strategy vs baseline."""

    evaluation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    baseline_procedure_id: uuid.UUID | None = None
    candidate_procedure_id: uuid.UUID
    evaluation_type: str = "SHADOW"
    baseline_metrics: dict[str, Any] = Field(default_factory=dict)
    candidate_metrics: dict[str, Any] = Field(default_factory=dict)
    metric_deltas: dict[str, Any] = Field(default_factory=dict)
    regression_detected: bool = False
    promotion_recommended: bool = False
    reasons: list[str] = Field(default_factory=list)
    status: str = "COMPLETED"
    created_at: datetime = Field(default_factory=utc_now)


class RollbackRequest(AegisBaseSchema):
    """Payload to safely roll back or disable a procedure."""

    target_version: int | None = Field(
        default=None,
        description="Version to restore. If omitted, restores immediate predecessor.",
    )
    reason: str = Field(..., min_length=3, description="Auditable justification for rollback.")


class RollbackResult(AegisBaseSchema):
    """Auditable result of a procedure rollback."""

    procedure_id: uuid.UUID
    rolled_back_from_version: int
    restored_to_version: int
    status: GovernanceProcedureStatus
    reason: str
    actor: str
    timestamp: datetime = Field(default_factory=utc_now)


class ApprovalDecisionRequest(AegisBaseSchema):
    """Human approval or rejection payload for high-risk procedure promotion."""

    decision: str = Field(..., description="'APPROVED' or 'REJECTED'")
    reason: str = Field(..., min_length=3)


class ProcedureVersionSnapshot(AegisBaseSchema):
    """Immutable version snapshot preserved for historical provenance and rollback."""

    version_id: uuid.UUID
    procedure_id: uuid.UUID
    version: int
    status: str
    validation_score: float
    confidence: float
    safety_classification: SafetyClassification
    snapshot: dict[str, Any]
    rollback_reason: str | None = None
    created_at: datetime


class GovernedProcedureDetail(AegisBaseSchema):
    """Complete detail view of a governed learned procedure."""

    procedure_id: uuid.UUID
    user_id: uuid.UUID
    task_domain: str
    name: str
    description: str
    trigger_conditions: list[str] = Field(default_factory=list)
    ordered_steps: list[dict[str, Any]] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float
    usage_count: int
    success_count: int
    failure_count: int
    version: int
    status: GovernanceProcedureStatus
    is_global: bool
    source_trajectory_ids: list[str] = Field(default_factory=list)
    source_evaluation_ids: list[str] = Field(default_factory=list)
    validation_score: float
    last_used_at: datetime | None = None
    promoted_at: datetime | None = None
    parent_procedure_id: uuid.UUID | None = None
    parent_version: int | None = None
    provenance_metadata: dict[str, Any] = Field(default_factory=dict)
    safety_classification: SafetyClassification = SafetyClassification.LOW
    approval_status: ApprovalStatus = ApprovalStatus.NONE
    approved_by: str | None = None
    approved_at: datetime | None = None
    procedure_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
