"""Unit tests for DelegationPlanner, DAG validation, depth checking, and cycle detection."""

import uuid

import pytest
from app.orchestration.delegation import DelegationPlanner
from app.orchestration.errors import CircularDelegationError, DelegationPlanError
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import DelegatedTask, DelegationPlan


def test_valid_dag_plan_generation() -> None:
    planner = DelegationPlanner()
    plan = planner.create_heuristic_plan(
        orchestration_id=uuid.uuid4(),
        objective="Analyze the numbers 10, 20, and 30",
    )
    assert len(plan.tasks) == 3
    assert plan.tasks[0].delegated_task_id == "task_analysis"
    assert plan.tasks[1].delegated_task_id == "task_verify"
    assert plan.tasks[2].delegated_task_id == "task_synthesis"
    assert "task_analysis" in plan.tasks[2].dependencies
    assert "task_verify" in plan.tasks[2].dependencies


def test_circular_dependency_detection_raises_error() -> None:
    planner = DelegationPlanner()
    orch_id = uuid.uuid4()

    # Cycle: A -> B -> C -> A
    tasks = [
        DelegatedTask(
            delegated_task_id="A",
            worker_id="w1",
            title="Task A",
            objective="Do A",
            dependencies=["C"],
        ),
        DelegatedTask(
            delegated_task_id="B",
            worker_id="w2",
            title="Task B",
            objective="Do B",
            dependencies=["A"],
        ),
        DelegatedTask(
            delegated_task_id="C",
            worker_id="w3",
            title="Task C",
            objective="Do C",
            dependencies=["B"],
        ),
    ]

    plan = DelegationPlan(
        orchestration_id=orch_id,
        objective="Circular task",
        tasks=tasks,
    )

    with pytest.raises(CircularDelegationError) as exc_info:
        planner.validate_plan(plan)
    assert "Circular dependency detected" in str(exc_info.value)


def test_self_dependency_raises_error() -> None:
    planner = DelegationPlanner()
    orch_id = uuid.uuid4()

    tasks = [
        DelegatedTask(
            delegated_task_id="A",
            worker_id="w1",
            title="Task A",
            objective="Do A",
            dependencies=["A"],
        ),
    ]

    plan = DelegationPlan(
        orchestration_id=orch_id,
        objective="Self dependency",
        tasks=tasks,
    )

    with pytest.raises(CircularDelegationError) as exc_info:
        planner.validate_plan(plan)
    assert "cannot depend on itself" in str(exc_info.value)


def test_missing_dependency_raises_error() -> None:
    planner = DelegationPlanner()
    orch_id = uuid.uuid4()

    tasks = [
        DelegatedTask(
            delegated_task_id="A",
            worker_id="w1",
            title="Task A",
            objective="Do A",
            dependencies=["NON_EXISTENT"],
        ),
    ]

    plan = DelegationPlan(
        orchestration_id=orch_id,
        objective="Missing dependency",
        tasks=tasks,
    )

    with pytest.raises(DelegationPlanError) as exc_info:
        planner.validate_plan(plan)
    assert "non-existent" in str(exc_info.value)


def test_max_workers_limit_enforced() -> None:
    policy = OrchestrationPolicy(max_workers=3)
    planner = DelegationPlanner(policy=policy)
    orch_id = uuid.uuid4()

    tasks = [
        DelegatedTask(
            delegated_task_id=f"t{i}",
            worker_id="w",
            title=f"Task {i}",
            objective=f"Objective {i}",
        )
        for i in range(5)
    ]

    plan = DelegationPlan(
        orchestration_id=orch_id,
        objective="Too many tasks",
        tasks=tasks,
    )

    with pytest.raises(DelegationPlanError) as exc_info:
        planner.validate_plan(plan)
    assert "exceeds maximum allowed workers" in str(exc_info.value)


def test_max_dependency_depth_enforced() -> None:
    policy = OrchestrationPolicy(max_dependency_depth=3, max_workers=6)
    planner = DelegationPlanner(policy=policy)
    orch_id = uuid.uuid4()

    # Depth 4: t1 -> t2 -> t3 -> t4
    tasks = [
        DelegatedTask(delegated_task_id="t1", worker_id="w", title="T1", objective="O1"),
        DelegatedTask(
            delegated_task_id="t2",
            worker_id="w",
            title="T2",
            objective="O2",
            dependencies=["t1"],
        ),
        DelegatedTask(
            delegated_task_id="t3",
            worker_id="w",
            title="T3",
            objective="O3",
            dependencies=["t2"],
        ),
        DelegatedTask(
            delegated_task_id="t4",
            worker_id="w",
            title="T4",
            objective="O4",
            dependencies=["t3"],
        ),
    ]

    plan = DelegationPlan(
        orchestration_id=orch_id,
        objective="Too deep DAG",
        tasks=tasks,
    )

    with pytest.raises(DelegationPlanError) as exc_info:
        planner.validate_plan(plan)
    assert "dependency depth" in str(exc_info.value)
