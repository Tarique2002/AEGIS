"""Phase 7 Multi-Agent Orchestration and Controlled Delegation schema migration.

Revision ID: 20260829_0005
Revises: 20260829_0004
Create Date: 2026-08-29 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0005"
down_revision: str | None = "20260829_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Orchestrations table
    op.create_table(
        "orchestrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="CREATED"),
        sa.Column("delegation_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("budget", sa.JSON(), nullable=False),
        sa.Column("final_result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("orchestration_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_orchestrations_task_id", "orchestrations", ["task_id"])
    op.create_index("ix_orchestrations_run_id", "orchestrations", ["run_id"])
    op.create_index("ix_orchestrations_user_id", "orchestrations", ["user_id"])
    op.create_index("ix_orchestrations_status", "orchestrations", ["status"])
    op.create_index("ix_orchestrations_idempotency_key", "orchestrations", ["idempotency_key"])

    # Delegated tasks table
    op.create_table(
        "delegated_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "orchestration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orchestrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worker_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("budget", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("task_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_delegated_tasks_orchestration_id", "delegated_tasks", ["orchestration_id"])
    op.create_index("ix_delegated_tasks_worker_type", "delegated_tasks", ["worker_type"])
    op.create_index("ix_delegated_tasks_status", "delegated_tasks", ["status"])

    # Worker executions table
    op.create_table(
        "worker_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "orchestration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orchestrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "delegated_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delegated_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column(
            "loop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_loops.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RUNNING"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("execution_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_worker_executions_orchestration_id", "worker_executions", ["orchestration_id"]
    )
    op.create_index(
        "ix_worker_executions_delegated_task_id", "worker_executions", ["delegated_task_id"]
    )
    op.create_index("ix_worker_executions_worker_id", "worker_executions", ["worker_id"])
    op.create_index("ix_worker_executions_loop_id", "worker_executions", ["loop_id"])
    op.create_index("ix_worker_executions_status", "worker_executions", ["status"])


def downgrade() -> None:
    op.drop_table("worker_executions")
    op.drop_table("delegated_tasks")
    op.drop_table("orchestrations")
