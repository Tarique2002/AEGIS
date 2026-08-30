"""Phase 6 Controlled Autonomous Agent Loop schema migration.

Revision ID: 20260829_0004
Revises: 20260829_0003
Create Date: 2026-08-29 16:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0004"
down_revision: str | None = "20260829_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Agent loops table
    op.create_table(
        "agent_loops",
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
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="CREATED"),
        sa.Column("iteration_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("autonomy_level", sa.String(length=50), nullable=False, server_default="BOUNDED"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("budget", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("final_result", sa.JSON(), nullable=True),
        sa.Column("loop_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
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
    op.create_index("ix_agent_loops_task_id", "agent_loops", ["task_id"])
    op.create_index("ix_agent_loops_run_id", "agent_loops", ["run_id"])
    op.create_index("ix_agent_loops_user_id", "agent_loops", ["user_id"])
    op.create_index("ix_agent_loops_status", "agent_loops", ["status"])
    op.create_index("ix_agent_loops_idempotency_key", "agent_loops", ["idempotency_key"])

    # Agent iterations table
    op.create_table(
        "agent_iterations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "loop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_loops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="RUNNING"),
        sa.Column("observation", sa.JSON(), nullable=True),
        sa.Column("decision", sa.JSON(), nullable=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("execution_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "evaluation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reflection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reflections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "iteration_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
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
    op.create_index("ix_agent_iterations_loop_id", "agent_iterations", ["loop_id"])
    op.create_index("ix_agent_iterations_iteration_number", "agent_iterations", ["iteration_number"])
    op.create_index("ix_agent_iterations_status", "agent_iterations", ["status"])
    op.create_index("ix_agent_iterations_plan_id", "agent_iterations", ["plan_id"])
    op.create_index("ix_agent_iterations_evaluation_id", "agent_iterations", ["evaluation_id"])
    op.create_index("ix_agent_iterations_reflection_id", "agent_iterations", ["reflection_id"])


def downgrade() -> None:
    op.drop_table("agent_iterations")
    op.drop_table("agent_loops")
