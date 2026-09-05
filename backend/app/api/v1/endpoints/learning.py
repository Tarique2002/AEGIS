"""FastAPI router endpoints for Phase 11 Self-Learning & Agent Evolution Engine."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_id
from app.db.session import get_db_session
from app.learning.schemas import (
    ExecutionTrajectory,
    LearnedProcedure,
    LearningSignal,
    LearningStatsResponse,
    OutcomeEvaluationResult,
    PromotionStatus,
    StrategyRecommendationQuery,
    StrategyRecommendationResponse,
    TrajectoryCreate,
)
from app.learning.service import SelfLearningService

router = APIRouter(prefix="/learning", tags=["Self-Learning Engine"])


def get_learning_service() -> SelfLearningService:
    return SelfLearningService()


@router.post(
    "/trajectories",
    response_model=ExecutionTrajectory,
    status_code=status.HTTP_201_CREATED,
    summary="Record execution trajectory",
    description="Sanitizes and captures a completed execution trajectory for learning.",
)
async def record_trajectory(
    create_data: TrajectoryCreate,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> ExecutionTrajectory:
    traj, _, _, _ = await service.process_completed_run(
        create_data=create_data,
        trusted_user_id=trusted_user_id,
        session=session,
    )
    await session.commit()
    return traj


@router.get(
    "/trajectories",
    response_model=list[ExecutionTrajectory],
    status_code=status.HTTP_200_OK,
    summary="List execution trajectories",
    description="Lists tenant-scoped execution trajectories.",
)
async def list_trajectories(
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ExecutionTrajectory]:
    return await service.list_trajectories(
        trusted_user_id=trusted_user_id,
        session=session,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/trajectories/{trajectory_id}",
    response_model=ExecutionTrajectory,
    status_code=status.HTTP_200_OK,
    summary="Get execution trajectory details",
    description="Fetches an execution trajectory ensuring tenant isolation.",
)
async def get_trajectory(
    trajectory_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> ExecutionTrajectory:
    traj = await service.get_trajectory(
        trajectory_id=trajectory_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
    if not traj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trajectory '{trajectory_id}' not found.",
        )
    return traj


@router.get(
    "/trajectories/{trajectory_id}/evaluation",
    response_model=OutcomeEvaluationResult,
    status_code=status.HTTP_200_OK,
    summary="Get trajectory outcome evaluation",
    description="Calculates deterministic outcome evaluation for an execution trajectory.",
)
async def get_trajectory_evaluation(
    trajectory_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> OutcomeEvaluationResult:
    traj = await service.get_trajectory(
        trajectory_id=trajectory_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
    if not traj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trajectory '{trajectory_id}' not found.",
        )
    return service.evaluator.evaluate(traj)


@router.get(
    "/signals",
    response_model=list[LearningSignal],
    status_code=status.HTTP_200_OK,
    summary="List learning signals",
    description="Fetches tenant-scoped distilled learning signals.",
)
async def list_signals(
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LearningSignal]:
    return await service.list_signals(
        trusted_user_id=trusted_user_id,
        session=session,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/procedures",
    response_model=list[LearnedProcedure],
    status_code=status.HTTP_200_OK,
    summary="List learned procedures",
    description="Fetches reusable strategies learned from successful executions.",
)
async def list_procedures(
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
    status_filter: Annotated[PromotionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LearnedProcedure]:
    return await service.list_procedures(
        trusted_user_id=trusted_user_id,
        session=session,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/procedures/{procedure_id}",
    response_model=LearnedProcedure,
    status_code=status.HTTP_200_OK,
    summary="Get learned procedure details",
    description="Retrieves a specific learned procedure with tenant isolation.",
)
async def get_procedure(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> LearnedProcedure:
    proc = await service.get_procedure(
        procedure_id=procedure_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
    if not proc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learned procedure '{procedure_id}' not found.",
        )
    return proc


@router.post(
    "/procedures/recommend",
    response_model=StrategyRecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Recommend strategies for a task",
    description="Ranks and returns learned procedures relevant to the given task objective.",
)
async def recommend_strategies(
    query: StrategyRecommendationQuery,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> StrategyRecommendationResponse:
    return await service.recommend_strategies(
        query=query,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/procedures/{procedure_id}/deprecate",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
    summary="Deprecate a learned procedure",
    description="Marks a procedure as deprecated so it is excluded from future recommendations.",
)
async def deprecate_procedure(
    procedure_id: uuid.UUID,
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> dict[str, bool]:
    success = await service.deprecate_procedure(
        procedure_id=procedure_id,
        trusted_user_id=trusted_user_id,
        session=session,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedure '{procedure_id}' not found or cannot be modified.",
        )
    await session.commit()
    return {"deprecated": True}


@router.get(
    "/stats",
    response_model=LearningStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get self-learning statistics",
    description="Returns aggregate learning and evolution metrics for the authenticated tenant.",
)
async def get_learning_stats(
    trusted_user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SelfLearningService, Depends(get_learning_service)],
) -> LearningStatsResponse:
    return await service.get_learning_stats(
        trusted_user_id=trusted_user_id,
        session=session,
    )
