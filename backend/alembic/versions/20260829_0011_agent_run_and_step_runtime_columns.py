"""Add runtime execution columns to agent_runs, task_steps, and execution_events.

Revision ID: 20260829_0011
Revises: 20260829_0010
Create Date: 2026-09-06 10:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260829_0011"
down_revision: str | None = "20260829_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # 1. agent_runs runtime execution columns
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS run_type VARCHAR(50) NOT NULL DEFAULT 'execution';")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS model_used VARCHAR(100);")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0;")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0;")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS total_tokens INTEGER NOT NULL DEFAULT 0;")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0;")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0;")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;")

        # 2. execution_events audit timestamp columns
        op.execute("ALTER TABLE execution_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
        op.execute("ALTER TABLE execution_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")

        # 3. task_steps planner execution columns
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS title VARCHAR(255) NOT NULL DEFAULT '';")
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS required_tools JSON NOT NULL DEFAULT '[]';")
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS dependencies JSON NOT NULL DEFAULT '[]';")
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS expected_output TEXT;")
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS result TEXT;")
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS error TEXT;")
        op.execute("ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;")
    else:
        # Generic / SQLite fallback using batch_alter_table
        with op.batch_alter_table("agent_runs") as batch_op:
            batch_op.add_column(sa.Column("run_type", sa.String(50), server_default="execution", nullable=False))
            batch_op.add_column(sa.Column("model_used", sa.String(100), nullable=True))
            batch_op.add_column(sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False))
            batch_op.add_column(sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False))
            batch_op.add_column(sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False))
            batch_op.add_column(sa.Column("estimated_cost_usd", sa.Float(), server_default="0.0", nullable=False))
            batch_op.add_column(sa.Column("latency_ms", sa.Float(), server_default="0.0", nullable=False))
            batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
            batch_op.add_column(sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))

        with op.batch_alter_table("execution_events") as batch_op:
            batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
            batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

        with op.batch_alter_table("task_steps") as batch_op:
            batch_op.add_column(sa.Column("title", sa.String(255), server_default="", nullable=False))
            batch_op.add_column(sa.Column("required_tools", sa.JSON(), server_default="[]", nullable=False))
            batch_op.add_column(sa.Column("dependencies", sa.JSON(), server_default="[]", nullable=False))
            batch_op.add_column(sa.Column("expected_output", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("result", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("error", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    pass
