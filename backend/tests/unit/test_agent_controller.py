"""Unit tests for AgentController multi-iteration orchestration and termination."""

import asyncio
import uuid

import pytest
from app.agent_loop.controller import AgentController
from app.agent_loop.iteration import AgentIterationRunner
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentLoopState, AgentLoopStatus, AutonomyLevel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.db.models.user import User
from app.evaluation.service import EvaluationService
from app.observability.events import EventEmitter
from app.planner.service import PlannerService
from app.schemas.common import utc_now
from app.tools.service import ToolService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_agent_controller_successful_loop(db_session: AsyncSession) -> None:
    user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    user = User(id=user_id, email="ctrl_test@example.com", hashed_password="pw", is_active=True)
    task = Task(
        id=task_id,
        user_id=user_id,
        objective="Calculate 10 * 10",
        status="running",
        task_metadata={},
    )
    run = AgentRun(
        id=run_id, task_id=task_id, run_type="LOOP", status="running", started_at=utc_now()
    )

    db_session.add(user)
    db_session.add(task)
    db_session.add(run)
    await db_session.commit()

    emitter = EventEmitter()
    tool_service = ToolService()
    planner_service = PlannerService(tool_service=tool_service, event_emitter=emitter)
    evaluation_service = EvaluationService(event_emitter=emitter)

    iteration_runner = AgentIterationRunner(
        planner_service=planner_service,
        evaluation_service=evaluation_service,
        event_emitter=emitter,
    )

    controller = AgentController(
        iteration_runner=iteration_runner,
        policy=AgentLoopPolicy(max_iterations=3),
        event_emitter=emitter,
    )

    loop_state = AgentLoopState(
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        objective="Calculate 10 * 10",
    )

    result_state = await controller.run_loop(
        loop_state=loop_state,
        autonomy_level=AutonomyLevel.BOUNDED,
        session=db_session,
    )

    assert result_state.status == AgentLoopStatus.COMPLETED
    assert len(result_state.completed_iterations) >= 1
    assert result_state.final_result is not None


@pytest.mark.asyncio
async def test_agent_controller_cancellation(db_session: AsyncSession) -> None:
    user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    user = User(id=user_id, email="ctrl_cancel@example.com", hashed_password="pw", is_active=True)
    task = Task(
        id=task_id, user_id=user_id, objective="Long task", status="running", task_metadata={}
    )
    run = AgentRun(
        id=run_id, task_id=task_id, run_type="LOOP", status="running", started_at=utc_now()
    )

    db_session.add(user)
    db_session.add(task)
    db_session.add(run)
    await db_session.commit()

    emitter = EventEmitter()
    planner_service = PlannerService(event_emitter=emitter)
    evaluation_service = EvaluationService(event_emitter=emitter)
    iteration_runner = AgentIterationRunner(
        planner_service=planner_service,
        evaluation_service=evaluation_service,
        event_emitter=emitter,
    )
    controller = AgentController(
        iteration_runner=iteration_runner,
        event_emitter=emitter,
    )

    loop_state = AgentLoopState(
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        objective="Cancelled loop",
    )

    cancel_token = asyncio.Event()
    cancel_token.set()  # Pre-cancelled

    result_state = await controller.run_loop(
        loop_state=loop_state,
        cancellation_token=cancel_token,
        session=db_session,
    )

    assert result_state.status == AgentLoopStatus.CANCELLED
