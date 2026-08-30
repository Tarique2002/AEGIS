"""Compliance Evidence & Attestation REST API Endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_principal
from app.compliance.exporters import ComplianceExporter
from app.compliance.schemas import (
    AuditIntegrityStatus,
    ComplianceControl,
    ComplianceEvidence,
    ComplianceReport,
    ComplianceReportCreate,
)
from app.compliance.service import ComplianceService
from app.core.auth import AuthenticatedPrincipal
from app.core.errors import AegisNotFoundError
from app.db.session import get_db_session

router = APIRouter(prefix="/compliance", tags=["compliance"])


def get_compliance_service() -> ComplianceService:
    return ComplianceService()


@router.get(
    "/controls",
    response_model=list[ComplianceControl],
    summary="List all compliance controls and their attestation status",
)
async def list_controls(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> list[ComplianceControl]:
    return await service.list_controls(principal, principal.user_id, session)


@router.post(
    "/report",
    response_model=ComplianceReport,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new compliance attestation report from verified evidence",
)
async def generate_compliance_report(
    payload: ComplianceReportCreate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> ComplianceReport:
    return await service.generate_report(
        principal=principal,
        tenant_id=principal.user_id,
        report_type=payload.report_type,
        start_time=payload.start_time,
        end_time=payload.end_time,
        session=session,
    )


@router.get(
    "/report",
    response_model=list[ComplianceReport],
    summary="List historical compliance reports for the tenant",
)
async def list_compliance_reports(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> list[ComplianceReport]:
    return await service.list_reports(principal, principal.user_id, session)


@router.get(
    "/report/{report_id}",
    response_model=ComplianceReport,
    summary="Fetch compliance report by ID",
)
async def get_compliance_report(
    report_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> ComplianceReport:
    try:
        return await service.get_report(principal, report_id, principal.user_id, session)
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compliance report not found."
        ) from None


@router.get(
    "/report/{report_id}/export/json",
    summary="Export compliance report as JSON with secret redaction",
)
async def export_report_json(
    report_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> Response:
    try:
        report = await service.get_report(principal, report_id, principal.user_id, session)
        json_content = ComplianceExporter.export_json(report)
        return Response(content=json_content, media_type="application/json")
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compliance report not found."
        ) from None


@router.get(
    "/report/{report_id}/export/csv",
    summary="Export compliance report as CSV with secret redaction",
)
async def export_report_csv(
    report_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> Response:
    try:
        report = await service.get_report(principal, report_id, principal.user_id, session)
        csv_content = ComplianceExporter.export_csv(report)
        return Response(content=csv_content, media_type="text/csv")
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compliance report not found."
        ) from None


@router.get(
    "/evidence/{evidence_id}",
    response_model=ComplianceEvidence,
    summary="Fetch compliance evidence item by ID",
)
async def get_compliance_evidence(
    evidence_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> ComplianceEvidence:
    try:
        return await service.get_evidence(principal, evidence_id, principal.user_id, session)
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compliance evidence not found."
        ) from None


@router.get(
    "/audit-integrity",
    response_model=AuditIntegrityStatus,
    summary="Check overall cryptographic audit chain integrity for tenant",
)
async def check_audit_integrity(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ComplianceService = Depends(get_compliance_service),
) -> AuditIntegrityStatus:
    return await service.check_audit_integrity(principal, principal.user_id, session)
