"""SQLAlchemy models for Controlled Autonomous Agent Loops and Iterations."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.evaluation import EvaluationModel, ReflectionModel
    from app.db.models.plan import ExecutionPlanModel
    from app.db.models.run import AgentRun
    from app.db.models.task import Task
    from app.db.models.user import User


class AgentLoopModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable entity representing a bounded autonomous agent loop session.
    Tracks state, cumulative resource consumption, current status, and outcomes.
    """

    __tablename__ = "agent_loops"

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
    status: Mapped[str] = mapped_column(String(50), default="CREATED", index=True, nullable=False)
    iteration_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    autonomy_level: Mapped[str] = mapped_column(String(50), default="BOUNDED", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    final_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    loop_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
    user: Mapped["User | None"] = relationship("User")
    iterations: Mapped[list["AgentIterationModel"]] = relationship(
        "AgentIterationModel",
        back_populates="loop",
        cascade="all, delete-orphan",
        order_by="AgentIterationModel.iteration_number.asc()",
    )


class AgentIterationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Audit record of an individual iteration pass within an autonomous loop.
    Captures observation, decision, plan ID, evaluation ID, reflection ID, and timestamps.
    """

    __tablename__ = "agent_iterations"

    loop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_loops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False, index=True)
    observation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execution_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reflection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reflections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    iteration_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    loop: Mapped["AgentLoopModel"] = relationship("AgentLoopModel", back_populates="iterations")
    plan: Mapped["ExecutionPlanModel | None"] = relationship("ExecutionPlanModel")
    evaluation: Mapped["EvaluationModel | None"] = relationship("EvaluationModel")
    reflection: Mapped["ReflectionModel | None"] = relationship("ReflectionModel")
