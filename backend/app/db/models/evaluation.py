"""SQLAlchemy models for Phase 4 Evaluation and Reflection records."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.run import AgentRun
    from app.db.models.task import Task


class EvaluationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable record of an agent execution evaluation pass.
    Stores numerical scores, criterion breakdowns, pass/fail status, and failure taxonomy.
    """

    __tablename__ = "evaluations"

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
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluator: Mapped[str] = mapped_column(String(100), nullable=False, default="composite")
    criterion_scores: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    failure_categories: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    weaknesses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recommendations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evaluation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
    reflection: Mapped["ReflectionModel | None"] = relationship(
        "ReflectionModel",
        back_populates="evaluation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ReflectionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable record of a structured post-run reflection.
    Stores observed facts, inferences, root causes, and actionable improvement suggestions.
    """

    __tablename__ = "reflections"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
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
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    what_went_well: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    what_went_wrong: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    root_causes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    improvement_suggestions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    reflection_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    evaluation: Mapped["EvaluationModel"] = relationship(
        "EvaluationModel", back_populates="reflection"
    )
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
