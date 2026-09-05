"""Phase 12 Production Learning Governance & Safe Evolution migration.

Revision ID: 20260829_0010
Revises: 20260829_0009
Create Date: 2026-08-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0010"
down_revision: str | None = "20260829_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add governance columns to learned_procedures
    op.add_column(
        "learned_procedures",
        sa.Column("source_trajectory_ids", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("source_evaluation_ids", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("validation_score", sa.Float(), server_default="0.0", nullable=False),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("parent_procedure_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_learned_procedures_parent_procedure_id",
        "learned_procedures",
        ["parent_procedure_id"],
    )
    op.add_column(
        "learned_procedures",
        sa.Column("parent_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("provenance_metadata", sa.JSON(), server_default="{}", nullable=False),
    )
    op.add_column(
        "learned_procedures",
        sa.Column(
            "safety_classification",
            sa.String(length=32),
            server_default="LOW",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_learned_procedures_safety_classification",
        "learned_procedures",
        ["safety_classification"],
    )
    op.add_column(
        "learned_procedures",
        sa.Column("approval_status", sa.String(length=32), server_default="NONE", nullable=False),
    )
    op.create_index(
        "ix_learned_procedures_approval_status",
        "learned_procedures",
        ["approval_status"],
    )
    op.add_column(
        "learned_procedures",
        sa.Column("approved_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "learned_procedures",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Create learned_procedure_versions table (for rollback & provenance)
    op.create_table(
        "learned_procedure_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "procedure_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learned_procedures.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("validation_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "safety_classification",
            sa.String(length=32),
            server_default="LOW",
            nullable=False,
        ),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )
    op.create_index(
        "ix_learned_procedure_versions_proc_ver",
        "learned_procedure_versions",
        ["procedure_id", "version"],
    )

    # 3. Create learning_governance_configs table
    op.create_table(
        "learning_governance_configs",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("min_evaluation_count", sa.Integer(), server_default="3", nullable=False),
        sa.Column("min_success_rate", sa.Float(), server_default="0.85", nullable=False),
        sa.Column("min_quality_score", sa.Float(), server_default="0.80", nullable=False),
        sa.Column("min_confidence", sa.Float(), server_default="0.80", nullable=False),
        sa.Column("max_regression_tolerance", sa.Float(), server_default="0.05", nullable=False),
        sa.Column(
            "require_human_approval_for_high_risk",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("drift_evaluation_window", sa.Integer(), server_default="20", nullable=False),
        sa.Column("drift_warning_threshold", sa.Float(), server_default="0.10", nullable=False),
        sa.Column("drift_critical_threshold", sa.Float(), server_default="0.20", nullable=False),
        sa.Column("config_metadata", sa.JSON(), server_default="{}", nullable=False),
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

    # 4. Create procedure_governance_evaluations table
    op.create_table(
        "procedure_governance_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "baseline_procedure_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learned_procedures.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "candidate_procedure_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learned_procedures.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "evaluation_type",
            sa.String(length=32),
            server_default="SHADOW",
            nullable=False,
            index=True,
        ),
        sa.Column("baseline_metrics", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("candidate_metrics", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("metric_deltas", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("regression_detected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("promotion_recommended", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="COMPLETED", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("procedure_governance_evaluations")
    op.drop_table("learning_governance_configs")
    op.drop_table("learned_procedure_versions")

    op.drop_index("ix_learned_procedures_approval_status", table_name="learned_procedures")
    op.drop_column("learned_procedures", "approved_at")
    op.drop_column("learned_procedures", "approved_by")
    op.drop_column("learned_procedures", "approval_status")
    op.drop_index("ix_learned_procedures_safety_classification", table_name="learned_procedures")
    op.drop_column("learned_procedures", "safety_classification")
    op.drop_column("learned_procedures", "provenance_metadata")
    op.drop_column("learned_procedures", "parent_version")
    op.drop_index("ix_learned_procedures_parent_procedure_id", table_name="learned_procedures")
    op.drop_column("learned_procedures", "parent_procedure_id")
    op.drop_column("learned_procedures", "promoted_at")
    op.drop_column("learned_procedures", "last_used_at")
    op.drop_column("learned_procedures", "validation_score")
    op.drop_column("learned_procedures", "source_evaluation_ids")
    op.drop_column("learned_procedures", "source_trajectory_ids")
