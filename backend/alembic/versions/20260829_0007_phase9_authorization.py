"""Phase 9 Dynamic Authorization, RBAC, and Audit Attestation migration.

Revision ID: 20260829_0007
Revises: 20260829_0006
Create Date: 2026-08-29 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0007"
down_revision: str | None = "20260829_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. authz_roles table
    op.create_table(
        "authz_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("is_system_role", sa.Boolean(), default=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_authz_roles_tenant_id", "authz_roles", ["tenant_id"])
    op.create_index("ix_authz_roles_enabled", "authz_roles", ["enabled"])

    # 2. authz_role_assignments table
    op.create_table(
        "authz_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("authz_roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_authz_role_assignments_user_id", "authz_role_assignments", ["user_id"])
    op.create_index("ix_authz_role_assignments_role_id", "authz_role_assignments", ["role_id"])
    op.create_index("ix_authz_role_assignments_tenant_id", "authz_role_assignments", ["tenant_id"])
    op.create_index("ix_authz_role_assignments_expires_at", "authz_role_assignments", ["expires_at"])
    op.create_index("ix_authz_role_assignments_enabled", "authz_role_assignments", ["enabled"])

    # 3. authz_policies table
    op.create_table(
        "authz_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), default="1.0.0", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), default=True, nullable=False),
        sa.Column("priority", sa.Integer(), default=100, nullable=False),
        sa.Column("effect", sa.String(20), default="ALLOW", nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_authz_policies_tenant_id", "authz_policies", ["tenant_id"])
    op.create_index("ix_authz_policies_enabled", "authz_policies", ["enabled"])
    op.create_index("ix_authz_policies_priority", "authz_policies", ["priority"])

    # 4. security_audit_chains table
    op.create_table(
        "security_audit_chains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(50), default="1.0.0", nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "sequence_number", name="uq_audit_chain_tenant_seq"),
    )
    op.create_index("ix_security_audit_chains_tenant_id", "security_audit_chains", ["tenant_id"])
    op.create_index("ix_security_audit_chains_user_id", "security_audit_chains", ["user_id"])
    op.create_index("ix_security_audit_chains_sequence_number", "security_audit_chains", ["sequence_number"])
    op.create_index("ix_security_audit_chains_event_type", "security_audit_chains", ["event_type"])
    op.create_index("ix_security_audit_chains_event_hash", "security_audit_chains", ["event_hash"])
    op.create_index("ix_security_audit_chains_timestamp", "security_audit_chains", ["timestamp"])


def downgrade() -> None:
    op.drop_table("security_audit_chains")
    op.drop_table("authz_policies")
    op.drop_table("authz_role_assignments")
    op.drop_table("authz_roles")
