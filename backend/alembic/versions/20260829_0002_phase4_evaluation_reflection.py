"""Phase 4 Evaluation and Reflection schema migration.

Revision ID: 20260829_0002
Revises: 20260829_0001
Create Date: 2026-08-29 11:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0002"
down_revision: str | None = "20260829_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Evaluations table
    op.create_table(
        "evaluations",
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
        sa.Column("overall_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("passed", sa.Boolean(), nullable=False, default=False),
        sa.Column("evaluator", sa.String(length=100), nullable=False, default="composite"),
        sa.Column("criterion_scores", sa.JSON(), nullable=False),
        sa.Column("failure_categories", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("evaluation_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_evaluations_id"), "evaluations", ["id"], unique=False)
    op.create_index(op.f("ix_evaluations_task_id"), "evaluations", ["task_id"], unique=False)
    op.create_index(op.f("ix_evaluations_run_id"), "evaluations", ["run_id"], unique=False)

    # Reflections table
    op.create_table(
        "reflections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evaluation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
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
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("what_went_well", sa.JSON(), nullable=False),
        sa.Column("what_went_wrong", sa.JSON(), nullable=False),
        sa.Column("root_causes", sa.JSON(), nullable=False),
        sa.Column("improvement_suggestions", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, default=1.0),
        sa.Column("reflection_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_reflections_id"), "reflections", ["id"], unique=False)
    op.create_index(
        op.f("ix_reflections_evaluation_id"), "reflections", ["evaluation_id"], unique=True
    )
    op.create_index(op.f("ix_reflections_task_id"), "reflections", ["task_id"], unique=False)
    op.create_index(op.f("ix_reflections_run_id"), "reflections", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reflections_run_id"), table_name="reflections")
    op.drop_index(op.f("ix_reflections_task_id"), table_name="reflections")
    op.drop_index(op.f("ix_reflections_evaluation_id"), table_name="reflections")
    op.drop_index(op.f("ix_reflections_id"), table_name="reflections")
    op.drop_table("reflections")

    op.drop_index(op.f("ix_evaluations_run_id"), table_name="evaluations")
    op.drop_index(op.f("ix_evaluations_task_id"), table_name="evaluations")
    op.drop_index(op.f("ix_evaluations_id"), table_name="evaluations")
    op.drop_table("evaluations")
