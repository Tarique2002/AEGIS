"""SQLAlchemy Task Model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.event import ExecutionEventModel
    from app.db.models.run import AgentRun
    from app.db.models.step import TaskStep
    from app.db.models.user import User


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents an autonomous agent task."""

    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True, nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User | None"] = relationship("User", back_populates="tasks")
    steps: Mapped[list["TaskStep"]] = relationship(
        "TaskStep",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskStep.step_order",
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun", back_populates="task", cascade="all, delete-orphan"
    )
    events: Mapped[list["ExecutionEventModel"]] = relationship(
        "ExecutionEventModel",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ExecutionEventModel.sequence_number",
    )
