"""Multi-Agent Orchestration and Controlled Delegation API endpoints."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_id
from app.db.session import get_db_session
from app.orchestration.dependencies import get_orchestration_service
from app.orchestration.schemas import (
    OrchestrationBudgetResponse,
    OrchestrationCreateRequest,
    OrchestrationResponse,
    OrchestrationResumeRequest,
    WorkerStateResponse,
)
from app.orchestration.service import OrchestrationService
from app.schemas.event import ExecutionEvent

router = APIRouter(prefix="/orchestrations", tags=["Multi-Agent Orchestration"])


@router.post(
    "",
    response_model=OrchestrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start multi-agent orchestration",
    description="Decomposes objective into specialized worker tasks via bounded DAG scheduling.",
)
async def create_orchestration(
    request: OrchestrationCreateRequest,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationResponse:
    return await service.run_orchestration(
        request=request,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{orchestration_id}",
    response_model=OrchestrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get orchestration status",
    description="Retrieves high-level orchestration state and final synthesis.",
)
async def get_orchestration(
    orchestration_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationResponse:
    return await service.get_orchestration(
        orchestration_id=orchestration_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{orchestration_id}/workers",
    response_model=list[WorkerStateResponse],
    status_code=status.HTTP_200_OK,
    summary="Get worker states",
    description="Retrieves individual worker task execution statuses, durations, and outputs.",
)
async def get_orchestration_workers(
    orchestration_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> list[WorkerStateResponse]:
    return await service.get_workers(
        orchestration_id=orchestration_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{orchestration_id}/results",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get validated worker results",
    description="Retrieves worker contributions, conflict records, and aggregated output.",
)
async def get_orchestration_results(
    orchestration_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> dict[str, Any]:
    return await service.get_results(
        orchestration_id=orchestration_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{orchestration_id}/events",
    response_model=list[ExecutionEvent],
    status_code=status.HTTP_200_OK,
    summary="Get orchestration event trace",
    description="Retrieves monotonic execution events emitted across the orchestration lifecycle.",
)
async def get_orchestration_events(
    orchestration_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> list[ExecutionEvent]:
    return await service.get_events(
        orchestration_id=orchestration_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{orchestration_id}/budget",
    response_model=OrchestrationBudgetResponse,
    status_code=status.HTTP_200_OK,
    summary="Get orchestration budget",
    description="Retrieves cumulative resource consumption and remaining allowances.",
)
async def get_orchestration_budget(
    orchestration_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationBudgetResponse:
    return await service.get_budget(
        orchestration_id=orchestration_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{orchestration_id}/resume",
    response_model=OrchestrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume or rework orchestration",
    description="Resumes orchestration or applies targeted rework from a persisted checkpoint.",
)
async def resume_orchestration(
    orchestration_id: uuid.UUID,
    request: OrchestrationResumeRequest | None = None,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)] = None,  # type: ignore[assignment]
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationResponse:
    req = request or OrchestrationResumeRequest()
    return await service.resume_orchestration(
        orchestration_id=orchestration_id,
        request=req,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{orchestration_id}/cancel",
    response_model=OrchestrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel active orchestration",
    description="Signals cancellation to stop pending and active worker tasks safely.",
)
async def cancel_orchestration(
    orchestration_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_db_session),
    service: OrchestrationService = Depends(get_orchestration_service),
) -> OrchestrationResponse:
    return await service.cancel_orchestration(
        orchestration_id=orchestration_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
