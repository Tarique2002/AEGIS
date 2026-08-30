"""FastAPI router endpoints for Safety Policies, Approvals, and Audit Logs."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.auth import AuthenticatedPrincipal
from app.db.session import get_db_session
from app.safety.dependencies import get_safety_policy, get_safety_service
from app.safety.policies import SafetyPolicy
from app.safety.schemas import (
    ApprovalCreateRequest,
    ApprovalResponse,
    SafetyAuditEvent,
)
from app.safety.service import SafetyService

router = APIRouter(prefix="/safety", tags=["Safety & Risk Control"])


@router.get(
    "/policy",
    response_model=SafetyPolicy,
    summary="Get effective platform safety policy",
)
async def get_effective_policy(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    policy: Annotated[SafetyPolicy, Depends(get_safety_policy)],
) -> SafetyPolicy:
    """Retrieve active safety policy and risk thresholds."""
    return policy


@router.get(
    "/status",
    summary="Get active safety status",
)
async def get_safety_status(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    service: Annotated[SafetyService, Depends(get_safety_service)],
) -> dict[str, str | bool]:
    """Retrieve operational status of safety subsystem."""
    return {
        "status": "active",
        "safety_enabled": True,
        "policy_version": service.policy.policy_version,
        "environment": service.policy.environment,
    }


@router.get(
    "/audit",
    response_model=list[SafetyAuditEvent],
    summary="Get authorized safety audit records",
)
async def get_safety_audit_records(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    service: Annotated[SafetyService, Depends(get_safety_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SafetyAuditEvent]:
    """Retrieve tenant-scoped append-only safety audit records."""
    return await service.get_audit_records(
        trusted_user_id=principal.user_id,
        session=session,
        limit=limit,
    )


@router.post(
    "/approvals",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create approval request for high-risk action",
)
async def create_approval_request(
    request: ApprovalCreateRequest,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    service: Annotated[SafetyService, Depends(get_safety_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalResponse:
    """Submit an action approval request for human-in-the-loop authorization."""
    return await service.create_approval(
        request=request,
        trusted_user_id=principal.user_id,
        session=session,
    )


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalResponse,
    summary="Get approval request status",
)
async def get_approval_request(
    approval_id: uuid.UUID,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    service: Annotated[SafetyService, Depends(get_safety_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalResponse:
    """Retrieve approval status with tenant isolation."""
    return await service.get_approval(
        approval_id=approval_id,
        trusted_user_id=principal.user_id,
        session=session,
    )


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve pending high-risk action",
)
async def approve_action_request(
    approval_id: uuid.UUID,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    service: Annotated[SafetyService, Depends(get_safety_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalResponse:
    """Explicitly grant human approval for a pending action within expiration bounds."""
    return await service.approve_action(
        approval_id=approval_id,
        trusted_user_id=principal.user_id,
        session=session,
    )


@router.post(
    "/approvals/{approval_id}/deny",
    response_model=ApprovalResponse,
    summary="Deny pending high-risk action",
)
async def deny_action_request(
    approval_id: uuid.UUID,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    service: Annotated[SafetyService, Depends(get_safety_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalResponse:
    """Explicitly deny approval for an action."""
    return await service.deny_action(
        approval_id=approval_id,
        trusted_user_id=principal.user_id,
        session=session,
    )
