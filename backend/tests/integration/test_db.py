"""Integration tests for database models, migrations metadata, and entity relationships."""

from datetime import UTC, datetime

from app.db.models import AgentRun, Task, TaskStep, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


async def test_user_task_step_run_lifecycle(db_session: AsyncSession):
    # 1. Create a user
    user = User(
        email="engineer@aegis.dev",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    assert user.id is not None
    assert user.created_at.tzinfo == UTC

    # 2. Create a task
    task = Task(
        user_id=user.id,
        objective="Perform multi-source comparative analysis",
        status="planning",
        task_metadata={"priority": "high", "domain": "ai_research"},
    )
    db_session.add(task)
    await db_session.flush()

    assert task.id is not None
    assert task.status == "planning"

    # 3. Create task steps
    step1 = TaskStep(
        task_id=task.id,
        step_order=1,
        title="Literature search",
        description="Query academic publications",
        status="completed",
        required_tools=["arxiv_search"],
        dependencies=[],
        expected_output="Top 5 papers",
        result="Found 5 papers with citation scores > 100",
    )
    step2 = TaskStep(
        task_id=task.id,
        step_order=2,
        title="Synthesize findings",
        description="Summarize architectural tradeoffs",
        status="pending",
        required_tools=[],
        dependencies=["step_1"],
    )
    db_session.add_all([step1, step2])
    await db_session.flush()

    # 4. Create an agent run
    run = AgentRun(
        task_id=task.id,
        run_type="PLANNING",
        model_used="gpt-4o",
        prompt_tokens=450,
        completion_tokens=120,
        total_tokens=570,
        estimated_cost_usd=0.004,
        latency_ms=850.0,
        status="completed",
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()

    # 5. Query back with eager relationships
    stmt = (
        select(Task)
        .where(Task.id == task.id)
        .options(selectinload(Task.steps), selectinload(Task.runs), selectinload(Task.user))
    )
    result = await db_session.execute(stmt)
    retrieved_task = result.scalar_one()

    assert retrieved_task.objective == "Perform multi-source comparative analysis"
    assert retrieved_task.user is not None
    assert retrieved_task.user.email == "engineer@aegis.dev"
    assert len(retrieved_task.steps) == 2
    assert retrieved_task.steps[0].title == "Literature search"
    assert retrieved_task.steps[0].required_tools == ["arxiv_search"]
    assert len(retrieved_task.runs) == 1
    assert retrieved_task.runs[0].run_type == "PLANNING"
    assert retrieved_task.runs[0].total_tokens == 570
