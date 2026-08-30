"""Phase 5 Planner & Execution Graph schema migration.

Revision ID: 20260829_0003
Revises: 20260829_0002
Create Date: 2026-08-29 12:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0003"
down_revision: str | None = "20260829_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Execution plans table
    op.create_table(
        "execution_plans",
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
        sa.Column("version", sa.Integer(), nullable=False, default=1),
        sa.Column("status", sa.String(length=50), nullable=False, default="DRAFT"),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("plan_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_execution_plans_id"), "execution_plans", ["id"], unique=False)
    op.create_index(op.f("ix_execution_plans_task_id"), "execution_plans", ["task_id"], unique=False)
    op.create_index(op.f("ix_execution_plans_run_id"), "execution_plans", ["run_id"], unique=False)
    op.create_index(op.f("ix_execution_plans_user_id"), "execution_plans", ["user_id"], unique=False)
    op.create_index(op.f("ix_execution_plans_status"), "execution_plans", ["status"], unique=False)

    # Execution nodes table
    op.create_table(
        "execution_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("execution_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, default="PENDING"),
        sa.Column("attempt", sa.Integer(), nullable=False, default=1),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("node_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_execution_nodes_id"), "execution_nodes", ["id"], unique=False)
    op.create_index(op.f("ix_execution_nodes_plan_id"), "execution_nodes", ["plan_id"], unique=False)
    op.create_index(op.f("ix_execution_nodes_node_id"), "execution_nodes", ["node_id"], unique=False)
    op.create_index(op.f("ix_execution_nodes_status"), "execution_nodes", ["status"], unique=False)

    # Execution checkpoints table
    op.create_table(
        "execution_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("execution_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("completed_nodes", sa.JSON(), nullable=False),
        sa.Column("node_states", sa.JSON(), nullable=False),
        sa.Column("node_outputs", sa.JSON(), nullable=False),
        sa.Column("checkpoint_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_execution_checkpoints_id"), "execution_checkpoints", ["id"], unique=False)
    op.create_index(
        op.f("ix_execution_checkpoints_plan_id"), "execution_checkpoints", ["plan_id"], unique=False
    )
    op.create_index(
        op.f("ix_execution_checkpoints_task_id"), "execution_checkpoints", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_execution_checkpoints_run_id"), "execution_checkpoints", ["run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_execution_checkpoints_run_id"), table_name="execution_checkpoints")
    op.drop_index(op.f("ix_execution_checkpoints_task_id"), table_name="execution_checkpoints")
    op.drop_index(op.f("ix_execution_checkpoints_plan_id"), table_name="execution_checkpoints")
    op.drop_index(op.f("ix_execution_checkpoints_id"), table_name="execution_checkpoints")
    op.drop_table("execution_checkpoints")

    op.drop_index(op.f("ix_execution_nodes_status"), table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_node_id"), table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_plan_id"), table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_id"), table_name="execution_nodes")
    op.drop_table("execution_nodes")

    op.drop_index(op.f("ix_execution_plans_status"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_user_id"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_run_id"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_task_id"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_id"), table_name="execution_plans")
    op.drop_table("execution_plans")
