"""FastAPI endpoints for Task Planning and Execution Graph orchestration."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_id
from app.db.session import get_db_session
from app.planner.schemas import (
    ExecutionPlan,
    PlanCreateRequest,
    PlanExecuteRequest,
    PlanExecutionResponse,
    PlanNodeExecutionRecord,
)
from app.planner.service import PlannerService

router = APIRouter(prefix="/plans", tags=["Planning & Execution Graph"])


def get_planner_service() -> PlannerService:
    """Dependency provider for PlannerService."""
    return PlannerService()


@router.post(
    "",
    response_model=ExecutionPlan,
    status_code=status.HTTP_201_CREATED,
    summary="Create and validate an execution plan",
    description="Deconstructs an objective or validates provided DAG graph nodes for execution.",
)
async def create_plan(
    request: PlanCreateRequest,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: PlannerService = Depends(get_planner_service),
) -> ExecutionPlan:
    return await service.create_and_validate_plan(
        request=request,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{plan_id}",
    response_model=ExecutionPlan,
    status_code=status.HTTP_200_OK,
    summary="Get execution plan",
    description="Retrieves a specific execution plan with strict tenant ownership verification.",
)
async def get_plan(
    plan_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: PlannerService = Depends(get_planner_service),
) -> ExecutionPlan:
    return await service.get_plan(
        plan_id=plan_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{plan_id}/execute",
    response_model=PlanExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute plan DAG",
    description="Runs the execution graph with bounded concurrency and checkpointing.",
)
async def execute_plan(
    plan_id: uuid.UUID,
    request: PlanExecuteRequest | None = None,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: PlannerService = Depends(get_planner_service),
) -> PlanExecutionResponse:
    req = request or PlanExecuteRequest()
    return await service.execute_plan(
        plan_id=plan_id,
        request=req,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{plan_id}/cancel",
    response_model=ExecutionPlan,
    status_code=status.HTTP_200_OK,
    summary="Cancel active plan execution",
    description="Signals cancellation for an actively running graph execution.",
)
async def cancel_plan(
    plan_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: PlannerService = Depends(get_planner_service),
) -> ExecutionPlan:
    return await service.cancel_execution(
        plan_id=plan_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/{plan_id}/resume",
    response_model=PlanExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume execution from checkpoint",
    description=(
        "Recovers graph state from the latest checkpoint snapshot without "
        "re-running finished nodes."
    ),
)
async def resume_plan(
    plan_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: PlannerService = Depends(get_planner_service),
) -> PlanExecutionResponse:
    return await service.resume_plan(
        plan_id=plan_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{plan_id}/nodes",
    response_model=list[PlanNodeExecutionRecord],
    status_code=status.HTTP_200_OK,
    summary="Get node execution traces",
    description="Lists individual node execution attempts and audit outputs for a plan.",
)
async def get_node_executions(
    plan_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: PlannerService = Depends(get_planner_service),
) -> list[PlanNodeExecutionRecord]:
    return await service.get_node_executions(
        plan_id=plan_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
