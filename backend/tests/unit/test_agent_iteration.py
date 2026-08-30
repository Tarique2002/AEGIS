"""Unit tests for AgentIterationRunner."""

import uuid

import pytest
from app.agent_loop.budget import AgentBudget
from app.agent_loop.guardrails import ProgressTracker
from app.agent_loop.iteration import AgentIterationRunner
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentLoopState, AgentLoopStatus
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
async def test_iteration_runner_linear_execution(db_session: AsyncSession) -> None:
    user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    user = User(id=user_id, email="iter_test@example.com", hashed_password="pw", is_active=True)
    task = Task(
        id=task_id,
        user_id=user_id,
        objective="Calculate 20 + 30",
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

    runner = AgentIterationRunner(
        planner_service=planner_service,
        evaluation_service=evaluation_service,
        event_emitter=emitter,
    )

    policy = AgentLoopPolicy()
    budget = AgentBudget(policy=policy)
    tracker = ProgressTracker(policy=policy)

    loop_state = AgentLoopState(
        task_id=task_id,
        run_id=run_id,
        user_id=user_id,
        objective="Calculate 20 + 30",
    )

    import time

    start_time = time.time()

    record = await runner.execute_iteration(
        loop_state=loop_state,
        budget=budget,
        tracker=tracker,
        start_time=start_time,
        session=db_session,
    )

    assert record.iteration_number == 1
    assert record.status in (AgentLoopStatus.COMPLETED, AgentLoopStatus.EXECUTING)
    assert record.observation is not None
    assert record.decision is not None
    assert record.plan_id is not None
