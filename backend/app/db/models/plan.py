"""SQLAlchemy models for Phase 5 Execution Plans, Graph Nodes, and Checkpoints."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.run import AgentRun
    from app.db.models.task import Task
    from app.db.models.user import User


class ExecutionPlanModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable record of a structured multi-step execution plan and its DAG graph structure.
    """

    __tablename__ = "execution_plans"

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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True, nullable=False)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    plan_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
    user: Mapped["User | None"] = relationship("User")
    nodes: Mapped[list["ExecutionNodeModel"]] = relationship(
        "ExecutionNodeModel",
        back_populates="plan",
        cascade="all, delete-orphan",
    )
    checkpoints: Mapped[list["ExecutionCheckpointModel"]] = relationship(
        "ExecutionCheckpointModel",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="ExecutionCheckpointModel.created_at.desc()",
    )


class ExecutionNodeModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable execution trace record of an individual plan node execution pass.
    """

    __tablename__ = "execution_nodes"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execution_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    plan: Mapped["ExecutionPlanModel"] = relationship("ExecutionPlanModel", back_populates="nodes")


class ExecutionCheckpointModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable snapshot of graph execution state allowing deterministic resume and recovery.
    """

    __tablename__ = "execution_checkpoints"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execution_plans.id", ondelete="CASCADE"),
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
    completed_nodes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    node_states: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    node_outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checkpoint_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    plan: Mapped["ExecutionPlanModel"] = relationship(
        "ExecutionPlanModel", back_populates="checkpoints"
    )
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
