"""Unit tests for Phase 7 Multi-Agent Orchestration Pydantic schemas and typed contracts."""

import uuid

from app.memory.schemas import MemoryType
from app.orchestration.schemas import (
    AggregatedResult,
    ConflictRecord,
    ConflictResolutionMethod,
    DelegatedTask,
    DelegatedTaskStatus,
    DelegationExecutionMode,
    DelegationPlan,
    OrchestrationBudgetState,
    OrchestrationState,
    OrchestrationStatus,
    WorkerDefinition,
    WorkerResult,
    WorkerType,
)


def test_worker_definition_defaults() -> None:
    w = WorkerDefinition(
        name="Test Worker",
        worker_type=WorkerType.RESEARCH,
        allowed_tools=["search_memory"],
        allowed_memory_types=[MemoryType.EPISODIC],
    )
    assert w.worker_id.startswith("worker_")
    assert w.max_iterations == 5
    assert w.timeout_seconds == 120.0
    assert w.enabled is True


def test_delegated_task_validation() -> None:
    task = DelegatedTask(
        worker_id="worker_analysis",
        title="Analyze Data",
        objective="Run calculation",
        dependencies=["task_prev"],
    )
    assert task.delegated_task_id.startswith("task_")
    assert task.status == DelegatedTaskStatus.PENDING
    assert task.priority == 1
    assert task.is_optional is False


def test_delegation_plan_schema() -> None:
    orch_id = uuid.uuid4()
    plan = DelegationPlan(
        orchestration_id=orch_id,
        objective="Deconstruct problem",
        tasks=[
            DelegatedTask(
                delegated_task_id="t1",
                worker_id="w1",
                title="Task 1",
                objective="Objective 1",
            )
        ],
        execution_mode=DelegationExecutionMode.DEPENDENCY_GRAPH,
    )
    assert plan.orchestration_id == orch_id
    assert len(plan.tasks) == 1
    assert plan.max_parallel_workers == 3


def test_worker_result_and_conflict_record() -> None:
    res = WorkerResult(
        worker_id="w1",
        delegated_task_id="t1",
        worker_type=WorkerType.ANALYSIS,
        status=DelegatedTaskStatus.COMPLETED,
        result=42,
        confidence=0.95,
        evidence=["Math check passed"],
    )
    assert res.result == 42
    assert res.confidence == 0.95

    conflict = ConflictRecord(
        worker_ids=["w1", "w2"],
        task_ids=["t1", "t2"],
        claims=[{"worker": "w1", "value": 42}, {"worker": "w2", "value": 100}],
        resolution_method=ConflictResolutionMethod.EVIDENCE_PRIORITY,
    )
    assert conflict.resolution_method == ConflictResolutionMethod.EVIDENCE_PRIORITY
    assert len(conflict.claims) == 2


def test_aggregated_result_and_budget_state() -> None:
    orch_id = uuid.uuid4()
    budget = OrchestrationBudgetState(
        worker_count=3,
        completed_workers=3,
        total_iterations=6,
        total_tool_calls=4,
    )
    assert budget.worker_count == 3
    assert budget.total_iterations == 6

    agg = AggregatedResult(
        orchestration_id=orch_id,
        status=OrchestrationStatus.COMPLETED,
        final_output={"answer": 42},
        summary="Completed successfully",
        worker_contributions={"t1": 42},
    )
    assert agg.status == OrchestrationStatus.COMPLETED
    assert agg.confidence == 1.0


def test_orchestration_state_lifecycle() -> None:
    state = OrchestrationState(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        objective="Run orchestration",
    )
    assert state.status == OrchestrationStatus.CREATED
    assert state.budget.total_iterations == 0
