"""Phase 11 Self-Learning & Agent Evolution Engine migration.

Revision ID: 20260829_0009
Revises: 20260829_0008
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0009"
down_revision: str | None = "20260829_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create learning_trajectories table
    op.create_table(
        "learning_trajectories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("planning_steps", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("selected_tools", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("tool_calls_metadata", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("worker_involvement", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("intermediate_decisions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("failures", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("retries_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("final_outcome", sa.JSON(), nullable=True),
        sa.Column("is_success", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("duration_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("policy_decisions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evaluation_summary", sa.JSON(), nullable=True),
        sa.Column("trajectory_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 2. Create learning_signals table
    op.create_table(
        "learning_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "trajectory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_trajectories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("signal_type", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "domain", sa.String(length=100), server_default="general", nullable=False, index=True
        ),
        sa.Column("context", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("discourages_strategy", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 3. Create learned_procedures table
    op.create_table(
        "learned_procedures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "task_domain",
            sa.String(length=100),
            server_default="general",
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("trigger_conditions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("ordered_steps", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("required_tools", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("constraints", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("success_criteria", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.85", nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="PROMOTED", nullable=False, index=True
        ),
        sa.Column("is_global", sa.Boolean(), server_default="false", nullable=False, index=True),
        sa.Column("procedure_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 4. Create learning_promotion_audits table
    op.create_table(
        "learning_promotion_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("procedure_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("promoted", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=100), server_default="system", nullable=False),
        sa.Column("evaluation_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("validation_passed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("version_transition", sa.String(length=50), nullable=True),
        sa.Column("audit_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("learning_promotion_audits")
    op.drop_table("learned_procedures")
    op.drop_table("learning_signals")
    op.drop_table("learning_trajectories")
