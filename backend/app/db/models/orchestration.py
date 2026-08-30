"""SQLAlchemy models for Phase 7 Multi-Agent Orchestration and Controlled Delegation."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.loop import AgentLoopModel
    from app.db.models.run import AgentRun
    from app.db.models.task import Task
    from app.db.models.user import User


class OrchestrationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable entity representing a multi-agent orchestration session.
    Tracks delegated tasks, worker executions, budget, and synthesized outcome.
    """

    __tablename__ = "orchestrations"

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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="CREATED", nullable=False, index=True)
    delegation_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    final_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    orchestration_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
    user: Mapped["User"] = relationship("User")
    delegated_tasks: Mapped[list["DelegatedTaskModel"]] = relationship(
        "DelegatedTaskModel", back_populates="orchestration", cascade="all, delete-orphan"
    )
    worker_executions: Mapped[list["WorkerExecutionModel"]] = relationship(
        "WorkerExecutionModel", back_populates="orchestration", cascade="all, delete-orphan"
    )


class DelegatedTaskModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable entity representing an individual delegated sub-task.
    """

    __tablename__ = "delegated_tasks"

    orchestration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    orchestration: Mapped["OrchestrationModel"] = relationship(
        "OrchestrationModel", back_populates="delegated_tasks"
    )
    worker_executions: Mapped[list["WorkerExecutionModel"]] = relationship(
        "WorkerExecutionModel", back_populates="delegated_task", cascade="all, delete-orphan"
    )


class WorkerExecutionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Audit execution record of a worker executing a delegated task via Phase 6 AgentLoop.
    """

    __tablename__ = "worker_executions"

    orchestration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orchestrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delegated_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("delegated_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    loop_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_loops.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False, index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    orchestration: Mapped["OrchestrationModel"] = relationship(
        "OrchestrationModel", back_populates="worker_executions"
    )
    delegated_task: Mapped["DelegatedTaskModel"] = relationship(
        "DelegatedTaskModel", back_populates="worker_executions"
    )
    loop: Mapped["AgentLoopModel | None"] = relationship("AgentLoopModel")
