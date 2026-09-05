"""FastAPI REST router for Phase 12 Production Learning Governance."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, get_current_user_id
from app.core.auth import AuthenticatedPrincipal
from app.db.models.learning import (
    LearnedProcedureModel,
    ProcedureGovernanceEvaluationModel,
)
from app.db.session import get_db_session
from app.learning.governance.manager import LearningGovernanceManager
from app.learning.governance.schemas import (
    ApprovalDecisionRequest,
    DriftReport,
    GovernanceConfig,
    GovernanceConfigUpdate,
    GovernanceProcedureStatus,
    GovernedProcedureDetail,
    ProcedureVersionSnapshot,
    PromotionGateResult,
    RollbackRequest,
    RollbackResult,
    SafetyClassification,
    ShadowEvaluationRequest,
    ShadowEvaluationResult,
)
from app.learning.sanitizer import sanitize_data

router = APIRouter(prefix="/learning/governance", tags=["Learning Governance Engine"])


def get_governance_manager() -> LearningGovernanceManager:
    return LearningGovernanceManager()


def _model_to_detail(m: LearnedProcedureModel) -> GovernedProcedureDetail:
    """Convert LearnedProcedureModel to sanitized GovernedProcedureDetail."""
    return GovernedProcedureDetail(
        procedure_id=m.id,
        user_id=m.user_id,
        task_domain=m.task_domain,
        name=m.name,
        description=m.description,
        trigger_conditions=m.trigger_conditions or [],
        ordered_steps=sanitize_data(m.ordered_steps or []),
        required_tools=m.required_tools or [],
        constraints=m.constraints or [],
        success_criteria=m.success_criteria or [],
        confidence=m.confidence,
        usage_count=m.usage_count,
        success_count=m.success_count,
        failure_count=m.failure_count,
        version=m.version,
        status=GovernanceProcedureStatus(m.status),
        is_global=m.is_global,
        source_trajectory_ids=m.source_trajectory_ids or [],
        source_evaluation_ids=m.source_evaluation_ids or [],
        validation_score=m.validation_score,
        last_used_at=m.last_used_at,
        promoted_at=m.promoted_at,
        parent_procedure_id=m.parent_procedure_id,
        parent_version=m.parent_version,
        provenance_metadata=sanitize_data(m.provenance_metadata or {}),
        safety_classification=SafetyClassification(m.safety_classification),
        approval_status=m.approval_status,  # type: ignore
        approved_by=m.approved_by,
        approved_at=m.approved_at,
        procedure_metadata=sanitize_data(m.procedure_metadata or {}),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get(
    "/procedures",
    response_model=list[GovernedProcedureDetail],
    status_code=status.HTTP_200_OK,
    summary="List governed procedures",
    description="Lists learned procedures visible to tenant with governance metadata.",
)
async def list_governed_procedures(
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status_filter: Annotated[GovernanceProcedureStatus | None, Query(alias="status")] = None,
    domain_filter: Annotated[str | None, Query(alias="domain")] = None,
    risk_filter: Annotated[SafetyClassification | None, Query(alias="risk")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GovernedProcedureDetail]:
    stmt = select(LearnedProcedureModel).where(
        (LearnedProcedureModel.user_id == trusted_user_id)
        | (LearnedProcedureModel.is_global.is_(True))
    )
    if status_filter:
        stmt = stmt.where(LearnedProcedureModel.status == status_filter.value)
    if domain_filter:
        stmt = stmt.where(LearnedProcedureModel.task_domain == domain_filter)
    if risk_filter:
        stmt = stmt.where(LearnedProcedureModel.safety_classification == risk_filter.value)

    stmt = (
        stmt.order_by(
            desc(LearnedProcedureModel.confidence),
            desc(LearnedProcedureModel.updated_at),
        )
        .limit(limit)
        .offset(offset)
    )

    res = await session.execute(stmt)
    return [_model_to_detail(m) for m in res.scalars().all()]


@router.get(
    "/procedures/{procedure_id}",
    response_model=GovernedProcedureDetail,
    status_code=status.HTTP_200_OK,
    summary="Get governed procedure detail",
    description="Retrieves a procedure by ID ensuring strict tenant isolation.",
)
async def get_governed_procedure(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GovernedProcedureDetail:
    stmt = select(LearnedProcedureModel).where(
        LearnedProcedureModel.id == procedure_id,
        (LearnedProcedureModel.user_id == trusted_user_id)
        | (LearnedProcedureModel.is_global.is_(True)),
    )
    res = await session.execute(stmt)
    model = res.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedure '{procedure_id}' not found.",
        )
    return _model_to_detail(model)


@router.get(
    "/procedures/{procedure_id}/history",
    response_model=list[ProcedureVersionSnapshot],
    status_code=status.HTTP_200_OK,
    summary="Get procedure version history",
    description="Retrieves all immutable historical snapshots for a procedure.",
)
async def get_procedure_version_history(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> list[ProcedureVersionSnapshot]:
    try:
        snapshots = await manager.list_version_history(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
        )
        return [
            ProcedureVersionSnapshot(
                version_id=s.id,
                procedure_id=s.procedure_id,
                version=s.version,
                status=s.status,
                validation_score=s.validation_score,
                confidence=s.confidence,
                safety_classification=SafetyClassification(s.safety_classification),
                snapshot=sanitize_data(s.snapshot),
                rollback_reason=s.rollback_reason,
                created_at=s.created_at,
            )
            for s in snapshots
        ]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/procedures/{procedure_id}/validate",
    response_model=PromotionGateResult,
    status_code=status.HTTP_200_OK,
    summary="Validate procedure gates",
    description="Runs deterministic promotion gates against candidate procedure.",
)
async def validate_procedure(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> PromotionGateResult:
    try:
        res = await manager.validate_procedure(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
        )
        await session.commit()
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/procedures/{procedure_id}/request-promotion",
    response_model=PromotionGateResult,
    status_code=status.HTTP_200_OK,
    summary="Request procedure promotion",
    description="Submits procedure for promotion evaluation through deterministic gates.",
)
async def request_procedure_promotion(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> PromotionGateResult:
    try:
        res = await manager.request_promotion(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
            actor=principal.email or str(trusted_user_id),
        )
        await session.commit()
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/procedures/{procedure_id}/approve",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Approve high-risk procedure",
    description="Records human approval for HIGH or CRITICAL risk procedure.",
)
async def approve_procedure_promotion(
    procedure_id: uuid.UUID,
    approval: ApprovalDecisionRequest,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> dict[str, Any]:
    try:
        if approval.decision.upper() == "APPROVED":
            await manager.approve_promotion(
                procedure_id=procedure_id,
                tenant_id=trusted_user_id,
                session=session,
                approver=principal.email or str(trusted_user_id),
                reason=approval.reason,
            )
        elif approval.decision.upper() == "REJECTED":
            await manager.reject_promotion(
                procedure_id=procedure_id,
                tenant_id=trusted_user_id,
                session=session,
                actor=principal.email or str(trusted_user_id),
                reason=approval.reason,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Decision must be 'APPROVED' or 'REJECTED'.",
            )
        await session.commit()
        return {"procedure_id": procedure_id, "decision": approval.decision.upper()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/procedures/{procedure_id}/promote",
    response_model=GovernedProcedureDetail,
    status_code=status.HTTP_200_OK,
    summary="Promote procedure to production",
    description="Promotes procedure when deterministic gates and approvals are satisfied.",
)
async def promote_procedure(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> GovernedProcedureDetail:
    try:
        proc = await manager.promote_procedure(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
            actor=principal.email or str(trusted_user_id),
        )
        await session.commit()
        return _model_to_detail(proc)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/procedures/{procedure_id}/disable",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
    summary="Disable procedure",
    description="Disables an active procedure without deleting historical records.",
)
async def disable_procedure(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
    reason: Annotated[str, Query(min_length=3)] = "Operator disable",
) -> dict[str, bool]:
    try:
        await manager.disable_procedure(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
            reason=reason,
            actor=principal.email or str(trusted_user_id),
        )
        await session.commit()
        return {"disabled": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/procedures/{procedure_id}/rollback",
    response_model=RollbackResult,
    status_code=status.HTTP_200_OK,
    summary="Rollback procedure",
    description="Restores procedure to a previous known-good version snapshot.",
)
async def rollback_procedure(
    procedure_id: uuid.UUID,
    rollback: RollbackRequest,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> RollbackResult:
    try:
        res = await manager.rollback_procedure(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
            target_version=rollback.target_version,
            reason=rollback.reason,
            actor=principal.email or str(trusted_user_id),
        )
        await session.commit()
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get(
    "/procedures/{procedure_id}/drift",
    response_model=DriftReport,
    status_code=status.HTTP_200_OK,
    summary="Get procedure drift status",
    description="Monitors real-time learning drift comparing recent executions to baseline.",
)
async def get_procedure_drift(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> DriftReport:
    try:
        res = await manager.check_drift(
            procedure_id=procedure_id,
            tenant_id=trusted_user_id,
            session=session,
        )
        await session.commit()
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/evaluations/shadow",
    response_model=ShadowEvaluationResult,
    status_code=status.HTTP_200_OK,
    summary="Run shadow/regression evaluation",
    description="Evaluates candidate strategy against baseline using historical trajectories.",
)
async def run_shadow_evaluation(
    eval_req: ShadowEvaluationRequest,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> ShadowEvaluationResult:
    try:
        res = await manager.run_shadow_evaluation(
            candidate_id=eval_req.candidate_procedure_id,
            baseline_id=eval_req.baseline_procedure_id,
            tenant_id=trusted_user_id,
            session=session,
            sample_limit=eval_req.sample_limit,
        )
        await session.commit()
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=ShadowEvaluationResult,
    status_code=status.HTTP_200_OK,
    summary="Get shadow evaluation results",
    description="Fetches stored results of a shadow or regression evaluation.",
)
async def get_shadow_evaluation(
    evaluation_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShadowEvaluationResult:
    stmt = select(ProcedureGovernanceEvaluationModel).where(
        ProcedureGovernanceEvaluationModel.id == evaluation_id,
        ProcedureGovernanceEvaluationModel.user_id == trusted_user_id,
    )
    res = await session.execute(stmt)
    model = res.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation '{evaluation_id}' not found.",
        )
    return ShadowEvaluationResult(
        evaluation_id=model.id,
        baseline_procedure_id=model.baseline_procedure_id,
        candidate_procedure_id=model.candidate_procedure_id,
        evaluation_type=model.evaluation_type,
        baseline_metrics=sanitize_data(model.baseline_metrics or {}),
        candidate_metrics=sanitize_data(model.candidate_metrics or {}),
        metric_deltas=sanitize_data(model.metric_deltas or {}),
        regression_detected=model.regression_detected,
        promotion_recommended=model.promotion_recommended,
        status=model.status,
        created_at=model.created_at,
    )


@router.get(
    "/config",
    response_model=GovernanceConfig,
    status_code=status.HTTP_200_OK,
    summary="Get governance configuration",
    description="Fetches tenant-level learning governance thresholds.",
)
async def get_governance_config(
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> GovernanceConfig:
    return await manager.get_or_create_config(tenant_id=trusted_user_id, session=session)


@router.put(
    "/config",
    response_model=GovernanceConfig,
    status_code=status.HTTP_200_OK,
    summary="Update governance configuration",
    description="Updates tenant-level learning governance thresholds.",
)
async def update_governance_config(
    updates: GovernanceConfigUpdate,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    manager: Annotated[LearningGovernanceManager, Depends(get_governance_manager)],
) -> GovernanceConfig:
    res = await manager.update_config(
        tenant_id=trusted_user_id,
        updates=updates,
        session=session,
    )
    await session.commit()
    return res
