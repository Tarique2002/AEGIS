"""Phase 10 ABAC, CEL Policies, Compliance Reports, and Audit Checkpoints migration.

Revision ID: 20260829_0008
Revises: 20260829_0007
Create Date: 2026-08-29 23:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0008"
down_revision: str | None = "20260829_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update authz_policies table
    op.add_column(
        "authz_policies",
        sa.Column("policy_type", sa.String(20), server_default="COMBINED", nullable=False),
    )
    op.add_column(
        "authz_policies",
        sa.Column("cel_expression", sa.Text(), nullable=True),
    )

    # 2. Create authz_policy_versions table
    op.create_table(
        "authz_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("authz_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("policy_type", sa.String(20), default="COMBINED", nullable=False),
        sa.Column("effect", sa.String(20), default="ALLOW", nullable=False),
        sa.Column("priority", sa.Integer(), default=100, nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("cel_expression", sa.Text(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_authz_policy_versions_policy_id", "authz_policy_versions", ["policy_id"])
    op.create_index("ix_authz_policy_versions_tenant_id", "authz_policy_versions", ["tenant_id"])
    op.create_index("ix_authz_policy_versions_version", "authz_policy_versions", ["version"])

    # 3. Create compliance_reports table
    op.create_table(
        "compliance_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_type", sa.String(50), default="SOC2_HIPAA", nullable=False),
        sa.Column("reporting_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reporting_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_count", sa.Integer(), default=0, nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("report_hash", sa.String(64), nullable=False),
        sa.Column("audit_chain_head", sa.String(64), nullable=False),
        sa.Column("verification_status", sa.String(50), default="VERIFIED", nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_compliance_reports_tenant_id", "compliance_reports", ["tenant_id"])

    # 4. Create compliance_evidence table
    op.create_table(
        "compliance_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("control_id", sa.String(50), nullable=False),
        sa.Column("evidence_type", sa.String(100), nullable=False),
        sa.Column("source_event_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("verification_status", sa.String(50), default="VERIFIED", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_compliance_evidence_tenant_id", "compliance_evidence", ["tenant_id"])
    op.create_index("ix_compliance_evidence_control_id", "compliance_evidence", ["control_id"])

    # 5. Create security_audit_checkpoints table
    op.create_table(
        "security_audit_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_start", sa.Integer(), nullable=False),
        sa.Column("sequence_end", sa.Integer(), nullable=False),
        sa.Column("chain_head", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.String(50), default="HMAC-SHA256", nullable=False),
        sa.Column("key_id", sa.String(100), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signer_provider", sa.String(50), default="LOCAL", nullable=False),
        sa.Column("verification_status", sa.String(50), default="VALID", nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "sequence_start", "sequence_end", name="uq_checkpoint_tenant_range"),
    )
    op.create_index("ix_security_audit_checkpoints_tenant_id", "security_audit_checkpoints", ["tenant_id"])
    op.create_index("ix_security_audit_checkpoints_sequence_start", "security_audit_checkpoints", ["sequence_start"])
    op.create_index("ix_security_audit_checkpoints_sequence_end", "security_audit_checkpoints", ["sequence_end"])


def downgrade() -> None:
    op.drop_table("security_audit_checkpoints")
    op.drop_table("compliance_evidence")
    op.drop_table("compliance_reports")
    op.drop_table("authz_policy_versions")
    op.drop_column("authz_policies", "cel_expression")
    op.drop_column("authz_policies", "policy_type")
