"""SQLAlchemy models for Phase 8 Safety Gates, Approvals, and Audit Logging."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.orchestration import OrchestrationModel
    from app.db.models.run import AgentRun
    from app.db.models.task import Task
    from app.db.models.user import User


class SafetyAuditModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Append-oriented audit record for all safety evaluations, gate decisions,
    and policy enforcement events.
    """

    __tablename__ = "safety_audits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    orchestration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    gate: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")

    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="selectin")
    task: Mapped["Task | None"] = relationship("Task", foreign_keys=[task_id], lazy="selectin")
    run: Mapped["AgentRun | None"] = relationship(
        "AgentRun", foreign_keys=[run_id], lazy="selectin"
    )
    orchestration: Mapped["OrchestrationModel | None"] = relationship(
        "OrchestrationModel", foreign_keys=[orchestration_id], lazy="selectin"
    )


class ApprovalModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Explicit authorization and human-in-the-loop approval record for high-risk actions.
    Bound to specific action, resource, user, and expiration timeout.
    """

    __tablename__ = "safety_approvals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    approval_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="selectin")
    task: Mapped["Task | None"] = relationship("Task", foreign_keys=[task_id], lazy="selectin")
