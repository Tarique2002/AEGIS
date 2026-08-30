"""Unit tests for DAGScheduler, cascade blocking, optional dependencies, and concurrency bounds."""

import uuid
from unittest.mock import AsyncMock

import pytest
from app.orchestration.scheduler import DAGScheduler
from app.orchestration.schemas import (
    DelegatedTask,
    DelegatedTaskStatus,
    DelegationPlan,
    OrchestrationBudgetState,
    WorkerResult,
)
from app.orchestration.worker import WorkerRunner


@pytest.mark.asyncio
async def test_scheduler_dag_execution_order() -> None:
    runner = AsyncMock(spec=WorkerRunner)
    execution_order: list[str] = []

    async def mock_execute(task: DelegatedTask, **kwargs: object) -> WorkerResult:
        execution_order.append(task.delegated_task_id)
        return WorkerResult(
            worker_id=task.worker_id,
            delegated_task_id=task.delegated_task_id,
            worker_type=task.worker_type,
            status=DelegatedTaskStatus.COMPLETED,
            result=f"Result of {task.delegated_task_id}",
            duration_ms=10.0,
        )

    runner.execute_task.side_effect = mock_execute
    scheduler = DAGScheduler(worker_runner=runner)

    plan = DelegationPlan(
        orchestration_id=uuid.uuid4(),
        objective="Run DAG",
        tasks=[
            DelegatedTask(delegated_task_id="T1", worker_id="w1", title="T1", objective="O1"),
            DelegatedTask(
                delegated_task_id="T2",
                worker_id="w2",
                title="T2",
                objective="O2",
                dependencies=["T1"],
            ),
            DelegatedTask(
                delegated_task_id="T3",
                worker_id="w3",
                title="T3",
                objective="O3",
                dependencies=["T2"],
            ),
        ],
    )

    budget = OrchestrationBudgetState()
    results = await scheduler.execute_plan(
        plan=plan,
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        trusted_user_id=uuid.uuid4(),
        session=AsyncMock(),
        budget=budget,
    )

    assert execution_order == ["T1", "T2", "T3"]
    assert len(results) == 3
    assert all(r.status == DelegatedTaskStatus.COMPLETED for r in results.values())
    assert budget.completed_workers == 3


@pytest.mark.asyncio
async def test_scheduler_cascade_blocking_on_required_failure() -> None:
    runner = AsyncMock(spec=WorkerRunner)

    async def mock_execute(task: DelegatedTask, **kwargs: object) -> WorkerResult:
        if task.delegated_task_id == "T1":
            return WorkerResult(
                worker_id=task.worker_id,
                delegated_task_id="T1",
                worker_type=task.worker_type,
                status=DelegatedTaskStatus.FAILED,
                error="Fatal error in T1",
            )
        return WorkerResult(
            worker_id=task.worker_id,
            delegated_task_id=task.delegated_task_id,
            worker_type=task.worker_type,
            status=DelegatedTaskStatus.COMPLETED,
            result="Success",
        )

    runner.execute_task.side_effect = mock_execute
    scheduler = DAGScheduler(worker_runner=runner)

    plan = DelegationPlan(
        orchestration_id=uuid.uuid4(),
        objective="Cascade fail",
        tasks=[
            DelegatedTask(delegated_task_id="T1", worker_id="w1", title="T1", objective="O1"),
            DelegatedTask(
                delegated_task_id="T2",
                worker_id="w2",
                title="T2",
                objective="O2",
                dependencies=["T1"],
                is_optional=False,
            ),
        ],
    )

    budget = OrchestrationBudgetState()
    results = await scheduler.execute_plan(
        plan=plan,
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        trusted_user_id=uuid.uuid4(),
        session=AsyncMock(),
        budget=budget,
    )

    assert results["T1"].status == DelegatedTaskStatus.FAILED
    assert results["T2"].status == DelegatedTaskStatus.BLOCKED
    assert "Required dependency failed" in str(results["T2"].error)


@pytest.mark.asyncio
async def test_scheduler_optional_dependency_failure_continues() -> None:
    runner = AsyncMock(spec=WorkerRunner)

    async def mock_execute(task: DelegatedTask, **kwargs: object) -> WorkerResult:
        if task.delegated_task_id == "T_optional":
            return WorkerResult(
                worker_id=task.worker_id,
                delegated_task_id="T_optional",
                worker_type=task.worker_type,
                status=DelegatedTaskStatus.FAILED,
                error="Optional failure",
            )
        return WorkerResult(
            worker_id=task.worker_id,
            delegated_task_id=task.delegated_task_id,
            worker_type=task.worker_type,
            status=DelegatedTaskStatus.COMPLETED,
            result="Success",
        )

    runner.execute_task.side_effect = mock_execute
    scheduler = DAGScheduler(worker_runner=runner)

    plan = DelegationPlan(
        orchestration_id=uuid.uuid4(),
        objective="Optional fail",
        tasks=[
            DelegatedTask(
                delegated_task_id="T_optional",
                worker_id="w1",
                title="Optional",
                objective="O_opt",
                is_optional=True,
            ),
            DelegatedTask(
                delegated_task_id="T_main",
                worker_id="w2",
                title="Main",
                objective="O_main",
                dependencies=["T_optional"],
            ),
        ],
    )

    budget = OrchestrationBudgetState()
    results = await scheduler.execute_plan(
        plan=plan,
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        trusted_user_id=uuid.uuid4(),
        session=AsyncMock(),
        budget=budget,
    )

    assert results["T_optional"].status == DelegatedTaskStatus.FAILED
    assert results["T_main"].status == DelegatedTaskStatus.COMPLETED
