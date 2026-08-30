"""Cryptographic Audit Chain and Verification REST API Endpoints."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_principal
from app.authz.service import AuthorizationService
from app.core.auth import AuthenticatedPrincipal
from app.db.models.authorization import AuditChainModel
from app.db.models.compliance import AuditCheckpointModel
from app.db.session import get_db_session
from app.schemas.common import utc_now
from app.security.audit_chain import AuditChainVerifier, AuditVerificationResult
from app.security.signing import CheckpointVerificationResult

router = APIRouter(prefix="/security/audit", tags=["audit-chain"])


def get_authz_service() -> AuthorizationService:
    return AuthorizationService()


class AuditChainEventResponse(BaseModel):
    """Structured audit chain record."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    sequence_number: int
    event_type: str
    action: str
    resource_type: str
    resource_id: str | None = None
    payload_hash: str
    previous_hash: str
    event_hash: str
    policy_version: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "",
    response_model=list[AuditChainEventResponse],
    summary="List cryptographic audit chain events for authenticated tenant",
)
async def list_audit_events(
    event_type: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    authz_service: AuthorizationService = Depends(get_authz_service),
) -> list[AuditChainEventResponse]:
    authz_service.require_scope(principal, "audit:read")
    await authz_service.require_permission(principal, "safety:audit", principal.user_id, session)

    stmt = select(AuditChainModel).where(AuditChainModel.tenant_id == principal.user_id)
    if event_type:
        stmt = stmt.where(AuditChainModel.event_type == event_type)
    if resource_type:
        stmt = stmt.where(AuditChainModel.resource_type == resource_type)
    if start_time:
        stmt = stmt.where(AuditChainModel.timestamp >= start_time)
    if end_time:
        stmt = stmt.where(AuditChainModel.timestamp <= end_time)

    stmt = stmt.order_by(desc(AuditChainModel.sequence_number)).limit(limit)
    res = await session.execute(stmt)
    records = res.scalars().all()

    return [
        AuditChainEventResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            user_id=r.user_id,
            sequence_number=r.sequence_number,
            event_type=r.event_type,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            payload_hash=r.payload_hash,
            previous_hash=r.previous_hash,
            event_hash=r.event_hash,
            policy_version=r.policy_version,
            timestamp=r.timestamp,
            metadata=r.audit_metadata,
        )
        for r in records
    ]


@router.get(
    "/verify",
    response_model=AuditVerificationResult,
    summary="Cryptographically verify append-only audit chain integrity for tenant",
)
async def verify_audit_chain(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    authz_service: AuthorizationService = Depends(get_authz_service),
) -> AuditVerificationResult:
    authz_service.require_scope(principal, "audit:read")
    await authz_service.require_permission(principal, "safety:audit", principal.user_id, session)

    return await AuditChainVerifier.verify_tenant_chain(
        tenant_id=principal.user_id,
        session=session,
    )


# ==============================================================================
# Signed Audit Checkpoints (Phase 10)
# ==============================================================================


class AuditCheckpointCreate(BaseModel):
    """Request payload to create a signed cryptographic audit checkpoint."""

    sequence_start: int | None = None
    sequence_end: int | None = None


class AuditCheckpointResponse(BaseModel):
    """Structured response for a signed audit checkpoint."""

    checkpoint_id: uuid.UUID
    tenant_id: uuid.UUID
    sequence_start: int
    sequence_end: int
    chain_head: str
    algorithm: str
    key_id: str
    signature: str
    signer_provider: str
    verification_status: str
    generated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/checkpoints",
    response_model=list[AuditCheckpointResponse],
    summary="List signed audit checkpoints for tenant",
)
async def list_checkpoints(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    authz_service: AuthorizationService = Depends(get_authz_service),
) -> list[AuditCheckpointResponse]:
    authz_service.require_scope(principal, "audit:read")
    await authz_service.require_permission(principal, "safety:audit", principal.user_id, session)

    stmt = (
        select(AuditCheckpointModel)
        .where(AuditCheckpointModel.tenant_id == principal.user_id)
        .order_by(desc(AuditCheckpointModel.generated_at))
    )
    res = await session.execute(stmt)
    checkpoints = res.scalars().all()

    return [
        AuditCheckpointResponse(
            checkpoint_id=cp.id,
            tenant_id=cp.tenant_id,
            sequence_start=cp.sequence_start,
            sequence_end=cp.sequence_end,
            chain_head=cp.chain_head,
            algorithm=cp.algorithm,
            key_id=cp.key_id,
            signature=cp.signature,
            signer_provider=cp.signer_provider,
            verification_status=cp.verification_status,
            generated_at=cp.generated_at,
            metadata=cp.checkpoint_metadata,
        )
        for cp in checkpoints
    ]


@router.post(
    "/checkpoints",
    response_model=AuditCheckpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new cryptographically signed audit checkpoint",
)
async def create_checkpoint(
    payload: AuditCheckpointCreate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    authz_service: AuthorizationService = Depends(get_authz_service),
) -> AuditCheckpointResponse:
    authz_service.require_scope(principal, "compliance:generate")
    await authz_service.require_permission(principal, "safety:audit", principal.user_id, session)

    # 1. Determine sequence range
    stmt = (
        select(AuditChainModel)
        .where(AuditChainModel.tenant_id == principal.user_id)
        .order_by(AuditChainModel.sequence_number.asc())
    )
    res = await session.execute(stmt)
    events = list(res.scalars().all())

    if not events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create checkpoint on empty audit chain.",
        )

    seq_start = (
        payload.sequence_start if payload.sequence_start is not None else events[0].sequence_number
    )
    seq_end = (
        payload.sequence_end if payload.sequence_end is not None else events[-1].sequence_number
    )

    # Find chain head at seq_end
    matching_events = [e for e in events if e.sequence_number == seq_end]
    if not matching_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audit event with sequence {seq_end} not found.",
        )
    chain_head = matching_events[0].event_hash

    # 2. Sign checkpoint payload using LocalSigningProvider
    from app.security.signing.local import LocalSigningProvider
    from app.security.signing.verifier import AuditCheckpointVerifier

    signer = LocalSigningProvider()
    payload_bytes = AuditCheckpointVerifier.construct_checkpoint_payload(
        tenant_id=principal.user_id,
        sequence_start=seq_start,
        sequence_end=seq_end,
        chain_head=chain_head,
    )
    signature, key_id = signer.sign(payload_bytes)

    # 3. Create AuditCheckpointModel
    cp_model = AuditCheckpointModel(
        id=uuid.uuid4(),
        tenant_id=principal.user_id,
        sequence_start=seq_start,
        sequence_end=seq_end,
        chain_head=chain_head,
        algorithm=signer.algorithm,
        key_id=key_id,
        signature=signature,
        signer_provider=signer.provider_type,
        verification_status="VALID",
        generated_at=utc_now(),
        checkpoint_metadata={
            "events_included": len([e for e in events if seq_start <= e.sequence_number <= seq_end])
        },
    )
    session.add(cp_model)
    await session.flush()

    return AuditCheckpointResponse(
        checkpoint_id=cp_model.id,
        tenant_id=cp_model.tenant_id,
        sequence_start=cp_model.sequence_start,
        sequence_end=cp_model.sequence_end,
        chain_head=cp_model.chain_head,
        algorithm=cp_model.algorithm,
        key_id=cp_model.key_id,
        signature=cp_model.signature,
        signer_provider=cp_model.signer_provider,
        verification_status=cp_model.verification_status,
        generated_at=cp_model.generated_at,
        metadata=cp_model.checkpoint_metadata,
    )


@router.get(
    "/checkpoints/{checkpoint_id}",
    response_model=AuditCheckpointResponse,
    summary="Fetch audit checkpoint details by ID",
)
async def get_checkpoint(
    checkpoint_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    authz_service: AuthorizationService = Depends(get_authz_service),
) -> AuditCheckpointResponse:
    authz_service.require_scope(principal, "audit:read")
    await authz_service.require_permission(principal, "safety:audit", principal.user_id, session)

    stmt = select(AuditCheckpointModel).where(
        AuditCheckpointModel.id == checkpoint_id,
        AuditCheckpointModel.tenant_id == principal.user_id,
    )
    res = await session.execute(stmt)
    cp = res.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found.")

    return AuditCheckpointResponse(
        checkpoint_id=cp.id,
        tenant_id=cp.tenant_id,
        sequence_start=cp.sequence_start,
        sequence_end=cp.sequence_end,
        chain_head=cp.chain_head,
        algorithm=cp.algorithm,
        key_id=cp.key_id,
        signature=cp.signature,
        signer_provider=cp.signer_provider,
        verification_status=cp.verification_status,
        generated_at=cp.generated_at,
        metadata=cp.checkpoint_metadata,
    )


@router.post(
    "/checkpoints/{checkpoint_id}/verify",
    response_model=CheckpointVerificationResult,
    summary="Cryptographically verify audit checkpoint signature and hash chain integrity",
)
async def verify_checkpoint(
    checkpoint_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    authz_service: AuthorizationService = Depends(get_authz_service),
) -> CheckpointVerificationResult:
    authz_service.require_scope(principal, "audit:read")
    await authz_service.require_permission(principal, "safety:audit", principal.user_id, session)

    stmt = select(AuditCheckpointModel).where(
        AuditCheckpointModel.id == checkpoint_id,
        AuditCheckpointModel.tenant_id == principal.user_id,
    )
    res = await session.execute(stmt)
    cp = res.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found.")

    from app.security.signing.verifier import AuditCheckpointVerifier

    return await AuditCheckpointVerifier.verify_checkpoint(cp, session)
