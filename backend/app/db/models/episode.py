"""SQLAlchemy model for Episodic Memory."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.run import AgentRun
    from app.db.models.task import Task
    from app.db.models.user import User


class EpisodicMemoryModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Persisted summary of an agent experience/run.
    Answers: 'What happened during this experience?'
    """

    __tablename__ = "episodic_memories"

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
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    observations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    memory_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
    task: Mapped["Task"] = relationship("Task")
    run: Mapped["AgentRun"] = relationship("AgentRun")
