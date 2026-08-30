"""Compliance Service orchestrating controls, evidence, reports, and audit integrity."""

import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.service import AuthorizationService
from app.compliance.controls import get_standard_controls
from app.compliance.reports import ReportGenerator
from app.compliance.schemas import (
    AuditIntegrityStatus,
    ComplianceControl,
    ComplianceEvidence,
    ComplianceReport,
    ComplianceReportSummary,
)
from app.core.auth import AuthenticatedPrincipal
from app.core.errors import AegisNotFoundError
from app.core.logging import get_logger
from app.db.models.compliance import ComplianceEvidenceModel, ComplianceReportModel
from app.schemas.event import ExecutionEventType
from app.security.audit_chain import AuditChainManager, AuditChainVerifier

logger = get_logger("aegis.compliance.service")


class ComplianceService:
    """Production Compliance Service managing attestations, evidence, and audit verification."""

    def __init__(self, authz_service: AuthorizationService | None = None) -> None:
        self.authz_service = authz_service or AuthorizationService()

    async def list_controls(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[ComplianceControl]:
        """List all defined compliance controls."""
        self.authz_service.require_scope(principal, "compliance:read")
        await self.authz_service.require_permission(principal, "safety:audit", tenant_id, session)
        return get_standard_controls()

    async def generate_report(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        report_type: str = "SOC2_HIPAA",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> ComplianceReport:
        """Generate a new cryptographic compliance report."""
        if not session:
            raise ValueError("AsyncSession required.")

        self.authz_service.require_scope(principal, "compliance:generate")
        await self.authz_service.require_permission(principal, "safety:audit", tenant_id, session)

        report = await ReportGenerator.generate_report(
            tenant_id=tenant_id,
            report_type=report_type,
            start_time=start_time,
            end_time=end_time,
            created_by=principal.user_id,
            session=session,
        )

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type=ExecutionEventType.COMPLIANCE_REPORT_GENERATED.value,
            action="generate_compliance_report",
            resource_type="compliance_report",
            resource_id=str(report.report_id),
            payload={
                "report_type": report.report_type,
                "report_hash": report.report_hash,
                "source_event_count": report.source_event_count,
                "verification_status": report.verification_status,
            },
            session=session,
        )
        return report

    async def get_report(
        self,
        principal: AuthenticatedPrincipal,
        report_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> ComplianceReport:
        """Fetch a previously generated compliance report."""
        self.authz_service.require_scope(principal, "compliance:read")
        await self.authz_service.require_permission(principal, "safety:audit", tenant_id, session)

        stmt = select(ComplianceReportModel).where(
            ComplianceReportModel.id == report_id,
            ComplianceReportModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Compliance report '{report_id}' not found.")

        # Reconstruct report structure
        summary = ComplianceReportSummary(**model.summary_json)
        controls = get_standard_controls()

        return ComplianceReport(
            report_id=model.id,
            tenant_id=model.tenant_id,
            report_type=model.report_type,
            reporting_period_start=model.reporting_period_start,
            reporting_period_end=model.reporting_period_end,
            source_event_count=model.source_event_count,
            source_hash=model.source_hash,
            report_hash=model.report_hash,
            audit_chain_head=model.audit_chain_head,
            verification_status=model.verification_status,
            summary=summary,
            controls=controls,
            evidence_items=[],
            generated_at=model.created_at,
            created_by=model.created_by,
        )

    async def list_reports(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[ComplianceReport]:
        """List historical compliance reports for the tenant."""
        self.authz_service.require_scope(principal, "compliance:read")
        await self.authz_service.require_permission(principal, "safety:audit", tenant_id, session)

        stmt = (
            select(ComplianceReportModel)
            .where(ComplianceReportModel.tenant_id == tenant_id)
            .order_by(desc(ComplianceReportModel.created_at))
        )
        res = await session.execute(stmt)
        models = res.scalars().all()

        reports = []
        controls = get_standard_controls()
        for m in models:
            summary = ComplianceReportSummary(**m.summary_json)
            reports.append(
                ComplianceReport(
                    report_id=m.id,
                    tenant_id=m.tenant_id,
                    report_type=m.report_type,
                    reporting_period_start=m.reporting_period_start,
                    reporting_period_end=m.reporting_period_end,
                    source_event_count=m.source_event_count,
                    source_hash=m.source_hash,
                    report_hash=m.report_hash,
                    audit_chain_head=m.audit_chain_head,
                    verification_status=m.verification_status,
                    summary=summary,
                    controls=controls,
                    evidence_items=[],
                    generated_at=m.created_at,
                    created_by=m.created_by,
                )
            )
        return reports

    async def get_evidence(
        self,
        principal: AuthenticatedPrincipal,
        evidence_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> ComplianceEvidence:
        """Fetch specific compliance evidence item."""
        self.authz_service.require_scope(principal, "compliance:read")
        await self.authz_service.require_permission(principal, "safety:audit", tenant_id, session)

        stmt = select(ComplianceEvidenceModel).where(
            ComplianceEvidenceModel.id == evidence_id,
            ComplianceEvidenceModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Compliance evidence '{evidence_id}' not found.")

        return ComplianceEvidence(
            evidence_id=model.id,
            tenant_id=model.tenant_id,
            control_id=model.control_id,
            evidence_type=model.evidence_type,
            source_event_ids=model.source_event_ids,
            evidence_hash=model.evidence_hash,
            verification_status=model.verification_status,
            metadata=model.evidence_metadata,
            generated_at=model.generated_at,
        )

    async def check_audit_integrity(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> AuditIntegrityStatus:
        """Check overall cryptographic audit chain integrity for tenant."""
        self.authz_service.require_scope(principal, "audit:read")
        await self.authz_service.require_permission(principal, "safety:audit", tenant_id, session)

        ver = await AuditChainVerifier.verify_tenant_chain(tenant_id, session)
        return AuditIntegrityStatus(
            tenant_id=tenant_id,
            chain_valid=ver.valid,
            total_events=ver.checked_events,
            chain_head=ver.chain_head or "none",
            failure_reason=ver.failure_reason,
            verified_at=ver.verified_at,
        )
