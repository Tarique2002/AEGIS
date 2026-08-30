"""Unit tests for WorkerResultCollector."""

import uuid

from app.orchestration.collector import WorkerResultCollector
from app.orchestration.schemas import (
    DelegatedTask,
    DelegatedTaskStatus,
    DelegationPlan,
    WorkerResult,
    WorkerType,
)


def test_collector_handles_missing_worker_results() -> None:
    plan = DelegationPlan(
        orchestration_id=uuid.uuid4(),
        objective="Collect tests",
        tasks=[
            DelegatedTask(delegated_task_id="T1", worker_id="w1", title="T1", objective="O1"),
            DelegatedTask(delegated_task_id="T2", worker_id="w2", title="T2", objective="O2"),
        ],
    )

    # Only T1 provided, T2 missing
    raw = {
        "T1": WorkerResult(
            worker_id="w1",
            delegated_task_id="T1",
            worker_type=WorkerType.GENERAL,
            status=DelegatedTaskStatus.COMPLETED,
            result="T1 Output",
        )
    }

    validated = WorkerResultCollector.collect_and_validate(plan, raw)
    assert len(validated) == 2
    assert validated["T1"].status == DelegatedTaskStatus.COMPLETED
    assert validated["T2"].status == DelegatedTaskStatus.FAILED
    assert "missing" in str(validated["T2"].error).lower()


def test_collector_extracts_successful_contributions() -> None:
    results = {
        "T1": WorkerResult(
            worker_id="w1",
            delegated_task_id="T1",
            worker_type=WorkerType.GENERAL,
            status=DelegatedTaskStatus.COMPLETED,
            result={"answer": 42},
        ),
        "T2": WorkerResult(
            worker_id="w2",
            delegated_task_id="T2",
            worker_type=WorkerType.GENERAL,
            status=DelegatedTaskStatus.FAILED,
            result=None,
        ),
    }

    contribs = WorkerResultCollector.extract_successful_contributions(results)
    assert contribs == {"T1": {"answer": 42}}
