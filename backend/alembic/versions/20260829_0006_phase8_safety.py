"""Phase 8 Safety Gates, Approvals, and Audit schema migration.

Revision ID: 20260829_0006
Revises: 20260829_0005
Create Date: 2026-08-29 18:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0006"
down_revision: str | None = "20260829_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Safety Audits table
    op.create_table(
        "safety_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "orchestration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orchestrations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("decision", sa.String(length=50), nullable=False),
        sa.Column("risk_level", sa.String(length=50), nullable=False),
        sa.Column("gate", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
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
        ),
    )
    op.create_index("ix_safety_audits_user_id", "safety_audits", ["user_id"])
    op.create_index("ix_safety_audits_task_id", "safety_audits", ["task_id"])
    op.create_index("ix_safety_audits_orchestration_id", "safety_audits", ["orchestration_id"])
    op.create_index("ix_safety_audits_created_at", "safety_audits", ["created_at"])

    # Safety Approvals table
    op.create_table(
        "safety_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("risk_level", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("policy_version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
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
        ),
    )
    op.create_index("ix_safety_approvals_user_id", "safety_approvals", ["user_id"])
    op.create_index("ix_safety_approvals_task_id", "safety_approvals", ["task_id"])
    op.create_index("ix_safety_approvals_status", "safety_approvals", ["status"])


def downgrade() -> None:
    op.drop_table("safety_approvals")
    op.drop_table("safety_audits")
