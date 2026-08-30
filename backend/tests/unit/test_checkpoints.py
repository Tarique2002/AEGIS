"""Unit tests for CheckpointManager and execution snapshot persistence."""

import uuid

import pytest
from app.db.models.plan import ExecutionPlanModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.planner.checkpoint import CheckpointManager
from app.planner.schemas import ExecutionContext, NodeStatus
from app.schemas.common import utc_now
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_checkpoint_save_and_retrieve(db_session: AsyncSession) -> None:
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    # Seed task, run, and plan in DB
    task = Task(id=task_id, objective="Test", status="running", task_metadata={})
    run = AgentRun(
        id=run_id,
        task_id=task_id,
        run_type="PLANNING",
        status="running",
        started_at=utc_now(),
    )
    plan_model = ExecutionPlanModel(
        id=plan_id,
        task_id=task_id,
        run_id=run_id,
        objective="Test plan",
        version=1,
        status="RUNNING",
        graph={},
        plan_metadata={},
    )
    db_session.add(task)
    db_session.add(run)
    db_session.add(plan_model)
    await db_session.commit()

    manager = CheckpointManager()
    ctx = ExecutionContext(
        task_id=task_id,
        run_id=run_id,
        user_id=uuid.uuid4(),
        plan_id=plan_id,
    )

    # Save checkpoint 1
    cp1 = await manager.save_checkpoint(
        context=ctx,
        completed_nodes=["node_1"],
        node_states={"node_1": NodeStatus.COMPLETED, "node_2": NodeStatus.READY},
        node_outputs={"node_1": {"result": 100, "api_key": "secret123"}},
        session=db_session,
    )
    await db_session.commit()

    assert "api_key" in cp1.node_outputs["node_1"]
    assert cp1.node_outputs["node_1"]["api_key"] == "[REDACTED]"

    # Save checkpoint 2
    await manager.save_checkpoint(
        context=ctx,
        completed_nodes=["node_1", "node_2"],
        node_states={"node_1": NodeStatus.COMPLETED, "node_2": NodeStatus.COMPLETED},
        node_outputs={"node_1": {"result": 100}, "node_2": "The result is 100."},
        session=db_session,
    )
    await db_session.commit()

    latest = await manager.get_latest_checkpoint(plan_id, db_session)
    assert latest is not None
    assert latest.completed_nodes == ["node_1", "node_2"]
    assert latest.node_states["node_2"] == NodeStatus.COMPLETED
