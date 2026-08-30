"""FastAPI router endpoints for Controlled Autonomous Agent Loops."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.schemas import (
    AgentBudgetResponse,
    AgentIterationResponse,
    AgentLoopCreateRequest,
    AgentLoopResponse,
    AgentLoopResumeRequest,
)
from app.agent_loop.service import AgentLoopService
from app.api.dependencies import get_current_user_id
from app.db.session import get_db_session
from app.schemas.event import ExecutionEvent

router = APIRouter(prefix="/agent-loops", tags=["Agent Loops"])


def get_agent_loop_service() -> AgentLoopService:
    """Dependency provider for AgentLoopService."""
    return AgentLoopService()


@router.post(
    "",
    response_model=AgentLoopResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and start an autonomous agent loop",
    description="Initiates a bounded, policy-controlled autonomous agent loop with hard limits.",
)
async def create_agent_loop(
    request: AgentLoopCreateRequest,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> AgentLoopResponse:
    if idempotency_key:
        request.idempotency_key = idempotency_key

    return await service.create_and_start_loop(
        request=request,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{loop_id}",
    response_model=AgentLoopResponse,
    status_code=status.HTTP_200_OK,
    summary="Get autonomous agent loop state",
    description="Fetches current loop state, status, iterations, and final outcomes.",
)
async def get_agent_loop(
    loop_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> AgentLoopResponse:
    return await service.get_loop(
        loop_id=loop_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{loop_id}/resume",
    response_model=AgentLoopResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume execution of an autonomous agent loop",
    description="Resumes loop execution from the latest checkpoint snapshot.",
)
async def resume_agent_loop(
    loop_id: uuid.UUID,
    request: AgentLoopResumeRequest,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> AgentLoopResponse:
    return await service.resume_loop(
        loop_id=loop_id,
        request=request,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{loop_id}/cancel",
    response_model=AgentLoopResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel an active autonomous agent loop",
    description="Signals non-destructive cancellation and marks loop as CANCELLED.",
)
async def cancel_agent_loop(
    loop_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> AgentLoopResponse:
    return await service.cancel_loop(
        loop_id=loop_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{loop_id}/iterations",
    response_model=list[AgentIterationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get loop iteration audit records",
    description="Lists all iteration records with observation and decision timestamps.",
)
async def get_agent_loop_iterations(
    loop_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> list[AgentIterationResponse]:
    return await service.get_iterations(
        loop_id=loop_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{loop_id}/budget",
    response_model=AgentBudgetResponse,
    status_code=status.HTTP_200_OK,
    summary="Get resource budget consumption and remaining limits",
    description="Inspects cumulative tool calls, LLM invocations, iterations, and limits.",
)
async def get_agent_loop_budget(
    loop_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> AgentBudgetResponse:
    return await service.get_budget(
        loop_id=loop_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{loop_id}/events",
    response_model=list[ExecutionEvent],
    status_code=status.HTTP_200_OK,
    summary="Get execution events for the loop",
    description="Retrieves monotonic trace event sequence for audit and telemetry.",
)
async def get_agent_loop_events(
    loop_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[AgentLoopService, Depends(get_agent_loop_service)] = None,  # type: ignore[assignment]
) -> list[ExecutionEvent]:
    return await service.get_events(
        loop_id=loop_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
