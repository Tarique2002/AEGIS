"""SQLAlchemy models for Phase 10 Compliance Reports, Evidence, and Signed Audit Checkpoints."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class ComplianceReportModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Generated compliance report with cryptographic attestation."""

    __tablename__ = "compliance_reports"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(50), default="SOC2_HIPAA", nullable=False)
    reporting_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reporting_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_chain_head: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="VERIFIED", nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ComplianceEvidenceModel(Base, UUIDPrimaryKeyMixin):
    """Structured compliance evidence item anchored to verified audit records."""

    __tablename__ = "compliance_evidence"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    control_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="VERIFIED", nullable=False)
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class AuditCheckpointModel(Base, UUIDPrimaryKeyMixin):
    """
    Cryptographically signed audit checkpoint over a sequence range of audit chain events.
    """

    __tablename__ = "security_audit_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "sequence_start", "sequence_end", name="uq_checkpoint_tenant_range"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_start: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sequence_end: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chain_head: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(50), default="HMAC-SHA256", nullable=False)
    key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signer_provider: Mapped[str] = mapped_column(String(50), default="LOCAL", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="VALID", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    checkpoint_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
