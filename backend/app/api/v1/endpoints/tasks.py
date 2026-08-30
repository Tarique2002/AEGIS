"""Task endpoints for submitting, querying, and auditing agent tasks."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import TaskService
from app.db.session import get_db_session
from app.schemas.event import ExecutionEvent
from app.schemas.task import TaskCreate, TaskExecutionResponse, TaskRead

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def get_task_service() -> TaskService:
    """Dependency provider for TaskService."""
    return TaskService()


@router.post(
    "",
    response_model=TaskExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit and execute an agent task",
    description="Submits an objective to AEGIS and executes a foundational agent pass.",
)
async def create_and_execute_task(
    task_in: TaskCreate,
    session: AsyncSession = Depends(get_db_session),
    service: TaskService = Depends(get_task_service),
) -> TaskExecutionResponse:
    return await service.create_and_execute_task(task_in, session=session)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    status_code=status.HTTP_200_OK,
    summary="Get task details",
    description="Retrieves a task by UUID including state, steps, and execution runs.",
)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    return await service.get_task_by_id(task_id, session=session)


@router.get(
    "/{task_id}/events",
    response_model=list[ExecutionEvent],
    status_code=status.HTTP_200_OK,
    summary="Get task execution event trace",
    description="Retrieves monotonically sequence-ordered execution trace events for a task.",
)
async def get_task_events(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    service: TaskService = Depends(get_task_service),
) -> list[ExecutionEvent]:
    return await service.get_task_events(task_id, session=session)
