"""Pydantic schemas for Compliance Controls, Evidence, and Reports."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema, utc_now


class ControlStatus(str, Enum):
    """Compliance verification status for a security control."""

    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ComplianceControl(AegisBaseSchema):
    """Security or compliance control definition."""

    control_id: str
    name: str
    description: str
    category: str
    evidence_sources: list[str] = Field(default_factory=list)
    status: ControlStatus = ControlStatus.COMPLIANT
    last_verified_at: datetime = Field(default_factory=utc_now)


class ComplianceEvidence(AegisBaseSchema):
    """Structured compliance evidence item anchored to verified audit records."""

    evidence_id: uuid.UUID
    tenant_id: uuid.UUID
    control_id: str
    evidence_type: str
    source_event_ids: list[str] = Field(default_factory=list)
    evidence_hash: str
    verification_status: str = "VERIFIED"
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)


class ComplianceReportCreate(AegisBaseSchema):
    """Request payload to generate a new compliance report."""

    report_type: str = "SOC2_HIPAA"
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=100, ge=1, le=500)


class ComplianceReportSummary(AegisBaseSchema):
    """Summary of control statuses within a compliance report."""

    total_controls: int = 0
    compliant_controls: int = 0
    non_compliant_controls: int = 0
    total_evidence_items: int = 0
    audit_chain_valid: bool = True


class ComplianceReport(AegisBaseSchema):
    """Structured compliance report with cryptographic attestation and source hashes."""

    report_id: uuid.UUID
    tenant_id: uuid.UUID
    report_type: str
    reporting_period_start: datetime
    reporting_period_end: datetime
    source_event_count: int
    source_hash: str
    report_hash: str
    audit_chain_head: str
    verification_status: str
    summary: ComplianceReportSummary
    controls: list[ComplianceControl] = Field(default_factory=list)
    evidence_items: list[ComplianceEvidence] = Field(default_factory=list)
    generated_at: datetime
    created_by: uuid.UUID | None = None


class AuditIntegrityStatus(AegisBaseSchema):
    """Audit chain integrity verification status for tenant."""

    tenant_id: uuid.UUID
    chain_valid: bool
    total_events: int
    chain_head: str
    failure_reason: str | None = None
    verified_at: datetime = Field(default_factory=utc_now)
