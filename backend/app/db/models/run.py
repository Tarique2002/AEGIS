"""SQLAlchemy AgentRun Model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.event import ExecutionEventModel
    from app.db.models.task import Task


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents an execution pass / iteration by the agent."""

    __tablename__ = "agent_runs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Run type (e.g. PLANNING, EXECUTION, EVALUATION, LEARNING)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="running", nullable=False)
    state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="runs")
    events: Mapped[list["ExecutionEventModel"]] = relationship(
        "ExecutionEventModel",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ExecutionEventModel.sequence_number",
    )
