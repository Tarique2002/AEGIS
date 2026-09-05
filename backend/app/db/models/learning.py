"""SQLAlchemy models for Phase 11 Self-Learning & Agent Evolution Engine."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.run import AgentRun
    from app.db.models.task import Task
    from app.db.models.user import User


class TrajectoryModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Execution trajectory capturing structured task lifecycle and tool usage."""

    __tablename__ = "learning_trajectories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    planning_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    selected_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tool_calls_metadata: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    worker_involvement: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    intermediate_decisions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    failures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    retries_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    policy_decisions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    evaluation_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trajectory_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")


class LearningSignalModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Distilled learning signal derived from an execution trajectory."""

    __tablename__ = "learning_signals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trajectory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_trajectories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(100), default="general", nullable=False, index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    discourages_strategy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
    trajectory: Mapped["TrajectoryModel"] = relationship("TrajectoryModel")


class LearnedProcedureModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative persistent record of a reusable learned strategy."""

    __tablename__ = "learned_procedures"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_domain: Mapped[str] = mapped_column(
        String(100), default="general", nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_conditions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ordered_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    required_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    success_criteria: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PROMOTED", nullable=False, index=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    procedure_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Governance attributes
    source_trajectory_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_evaluation_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    validation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    safety_classification: Mapped[str] = mapped_column(
        String(32), default="LOW", nullable=False, index=True
    )
    approval_status: Mapped[str] = mapped_column(
        String(32), default="NONE", nullable=False, index=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")


class LearnedProcedureVersionModel(Base, UUIDPrimaryKeyMixin):
    """Historical snapshot of a procedure version for audit and rollback."""

    __tablename__ = "learned_procedure_versions"

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learned_procedures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    validation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    safety_classification: Mapped[str] = mapped_column(
        String(32), default="LOW", nullable=False
    )
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class LearningGovernanceConfigModel(Base):
    """Tenant-configurable governance thresholds for learning and promotion."""

    __tablename__ = "learning_governance_configs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    min_evaluation_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    min_success_rate: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    min_quality_score: Mapped[float] = mapped_column(Float, default=0.80, nullable=False)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.80, nullable=False)
    max_regression_tolerance: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    require_human_approval_for_high_risk: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    drift_evaluation_window: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    drift_warning_threshold: Mapped[float] = mapped_column(Float, default=0.10, nullable=False)
    drift_critical_threshold: Mapped[float] = mapped_column(Float, default=0.20, nullable=False)
    config_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ProcedureGovernanceEvaluationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Auditable record of shadow, regression, and replay evaluations."""

    __tablename__ = "procedure_governance_evaluations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    baseline_procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learned_procedures.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_procedure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learned_procedures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_type: Mapped[str] = mapped_column(
        String(32), default="SHADOW", nullable=False, index=True
    )
    baseline_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    candidate_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metric_deltas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    regression_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promotion_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED", nullable=False)


class ProcedurePromotionAuditModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Audit log tracking validation, promotion, and version transition decisions."""

    __tablename__ = "learning_promotion_audits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    evaluation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version_transition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")

