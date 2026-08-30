"""Evaluation and Reflection API endpoints for AEGIS agent executions."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_id
from app.db.session import get_db_session
from app.evaluation.schemas import (
    EvaluationRequest,
    EvaluationResult,
    ReflectionRecord,
    ReflectionRequest,
)
from app.evaluation.service import EvaluationService

router = APIRouter(tags=["Evaluation & Reflection"])


def get_evaluation_service() -> EvaluationService:
    """Dependency provider for EvaluationService."""
    return EvaluationService()


@router.post(
    "/evaluations",
    response_model=EvaluationResult,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate an agent execution run",
    description=(
        "Inspects execution trace, telemetry, and output to produce a scored evaluation record."
    ),
)
async def create_evaluation(
    request: EvaluationRequest,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationResult:
    return await service.evaluate_run(
        request=request,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=EvaluationResult,
    status_code=status.HTTP_200_OK,
    summary="Get evaluation details",
    description="Retrieves a specific evaluation record with strict tenant ownership verification.",
)
async def get_evaluation(
    evaluation_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationResult:
    return await service.get_evaluation(
        evaluation_id=evaluation_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/tasks/{task_id}/evaluations",
    response_model=list[EvaluationResult],
    status_code=status.HTTP_200_OK,
    summary="List task evaluations",
    description="Retrieves all evaluation records associated with a specific task.",
)
async def get_task_evaluations(
    task_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: EvaluationService = Depends(get_evaluation_service),
) -> list[EvaluationResult]:
    return await service.get_task_evaluations(
        task_id=task_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/evaluations/{evaluation_id}/reflection",
    response_model=ReflectionRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Generate diagnostic reflection",
    description=(
        "Analyzes an evaluation result to generate root cause classifications "
        "and improvement suggestions."
    ),
)
async def create_reflection(
    evaluation_id: uuid.UUID,
    request: ReflectionRequest | None = None,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: EvaluationService = Depends(get_evaluation_service),
) -> ReflectionRecord:
    req = request or ReflectionRequest(evaluation_id=evaluation_id)
    return await service.generate_reflection(
        evaluation_id=evaluation_id,
        request=req,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/evaluations/{evaluation_id}/reflection",
    response_model=ReflectionRecord,
    status_code=status.HTTP_200_OK,
    summary="Get evaluation reflection",
    description="Retrieves the diagnostic reflection record associated with an evaluation.",
)
async def get_reflection(
    evaluation_id: uuid.UUID,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: EvaluationService = Depends(get_evaluation_service),
) -> ReflectionRecord:
    return await service.get_reflection_by_evaluation_id(
        evaluation_id=evaluation_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
