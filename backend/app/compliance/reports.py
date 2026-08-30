"""Deterministic Compliance Report Generator."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.controls import get_standard_controls
from app.compliance.evidence import EvidenceCollector
from app.compliance.schemas import (
    ComplianceEvidence,
    ComplianceReport,
    ComplianceReportSummary,
    ControlStatus,
)
from app.db.models.authorization import AuditChainModel
from app.db.models.compliance import ComplianceReportModel
from app.schemas.common import utc_now
from app.security.audit_chain import AuditChainVerifier


class ReportGenerator:
    """Generates verifiable, reproducible compliance reports with SHA-256 integrity hashes."""

    @staticmethod
    def compute_hash(data: dict) -> str:
        """Compute canonical SHA-256 hash for dictionary."""
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    async def generate_report(
        cls,
        tenant_id: uuid.UUID,
        report_type: str = "SOC2_HIPAA",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        created_by: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> ComplianceReport:
        """Generate a cryptographically anchored compliance report."""
        if not session:
            raise ValueError("AsyncSession required for report generation.")

        now = utc_now()
        period_end = end_time or now
        period_start = start_time or (period_end - timedelta(days=30))

        # 1. Verify underlying audit chain integrity
        chain_ver = await AuditChainVerifier.verify_tenant_chain(tenant_id, session)

        # 2. Fetch audit events in period
        stmt = (
            select(AuditChainModel)
            .where(
                AuditChainModel.tenant_id == tenant_id,
                AuditChainModel.timestamp >= period_start,
                AuditChainModel.timestamp <= period_end,
            )
            .order_by(AuditChainModel.sequence_number.asc())
        )
        res = await session.execute(stmt)
        events = list(res.scalars().all())

        # Compute source hash over event hashes
        source_hashes = [e.event_hash for e in events]
        source_hash = hashlib.sha256(":".join(source_hashes).encode("utf-8")).hexdigest()

        # 3. Collect evidence
        evidence_models = await EvidenceCollector.collect_evidence_for_tenant(
            tenant_id=tenant_id,
            start_time=period_start,
            end_time=period_end,
            session=session,
        )

        evidence_items = [
            ComplianceEvidence(
                evidence_id=em.id,
                tenant_id=em.tenant_id,
                control_id=em.control_id,
                evidence_type=em.evidence_type,
                source_event_ids=em.source_event_ids,
                evidence_hash=em.evidence_hash,
                verification_status=em.verification_status,
                metadata=em.evidence_metadata,
                generated_at=em.generated_at,
            )
            for em in evidence_models
        ]

        # 4. Evaluate controls
        controls = get_standard_controls()
        if not chain_ver.valid:
            # Mark audit controls as non-compliant if chain corrupted
            for c in controls:
                if c.category == "Audit":
                    c.status = ControlStatus.NON_COMPLIANT

        compliant_count = sum(1 for c in controls if c.status == ControlStatus.COMPLIANT)
        non_compliant_count = sum(1 for c in controls if c.status == ControlStatus.NON_COMPLIANT)

        summary = ComplianceReportSummary(
            total_controls=len(controls),
            compliant_controls=compliant_count,
            non_compliant_controls=non_compliant_count,
            total_evidence_items=len(evidence_items),
            audit_chain_valid=chain_ver.valid,
        )

        # 5. Compute deterministic report hash
        report_id = uuid.uuid4()
        report_dict = {
            "report_id": str(report_id),
            "tenant_id": str(tenant_id),
            "report_type": report_type,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source_hash": source_hash,
            "source_event_count": len(events),
            "chain_head": chain_ver.chain_head,
            "summary": summary.model_dump(),
        }
        report_hash = cls.compute_hash(report_dict)

        ver_status = "VERIFIED" if chain_ver.valid else "COMPROMISED"

        # 6. Save ComplianceReportModel
        report_model = ComplianceReportModel(
            id=report_id,
            tenant_id=tenant_id,
            report_type=report_type,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            source_event_count=len(events),
            source_hash=source_hash,
            report_hash=report_hash,
            audit_chain_head=chain_ver.chain_head,
            verification_status=ver_status,
            summary_json=summary.model_dump(),
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(report_model)
        await session.flush()

        return ComplianceReport(
            report_id=report_id,
            tenant_id=tenant_id,
            report_type=report_type,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            source_event_count=len(events),
            source_hash=source_hash,
            report_hash=report_hash,
            audit_chain_head=chain_ver.chain_head or "none",
            verification_status=ver_status,
            summary=summary,
            controls=controls,
            evidence_items=evidence_items,
            generated_at=now,
            created_by=created_by,
        )
