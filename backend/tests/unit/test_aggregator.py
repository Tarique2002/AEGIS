"""Unit tests for ResultAggregator, conflict detection, and provenance tracking."""

import uuid

from app.orchestration.aggregator import ResultAggregator
from app.orchestration.schemas import (
    DelegatedTaskStatus,
    OrchestrationStatus,
    WorkerResult,
    WorkerType,
)


def test_aggregator_synthesizes_successful_workers() -> None:
    aggregator = ResultAggregator()
    orch_id = uuid.uuid4()

    worker_results = {
        "task_analysis": WorkerResult(
            worker_id="worker_analysis",
            delegated_task_id="task_analysis",
            worker_type=WorkerType.ANALYSIS,
            status=DelegatedTaskStatus.COMPLETED,
            result={"sum": 60},
            confidence=0.95,
        ),
        "task_synthesis": WorkerResult(
            worker_id="worker_synthesis",
            delegated_task_id="task_synthesis",
            worker_type=WorkerType.SYNTHESIS,
            status=DelegatedTaskStatus.COMPLETED,
            result={"final_answer": "The sum of numbers is 60."},
            confidence=0.98,
        ),
    }

    agg = aggregator.aggregate(orch_id, worker_results)
    assert agg.status == OrchestrationStatus.COMPLETED
    assert agg.final_output == {"final_answer": "The sum of numbers is 60."}
    assert len(agg.conflicts) == 0
    assert len(agg.provenance) == 2


def test_aggregator_detects_contradictory_conflicts() -> None:
    aggregator = ResultAggregator()
    orch_id = uuid.uuid4()

    # Worker A claims 50, Worker B claims 60
    worker_results = {
        "task_1": WorkerResult(
            worker_id="worker_1",
            delegated_task_id="task_1",
            worker_type=WorkerType.ANALYSIS,
            status=DelegatedTaskStatus.COMPLETED,
            result={"total": 50},
        ),
        "task_2": WorkerResult(
            worker_id="worker_2",
            delegated_task_id="task_2",
            worker_type=WorkerType.ANALYSIS,
            status=DelegatedTaskStatus.COMPLETED,
            result={"total": 60},
        ),
    }

    agg = aggregator.aggregate(orch_id, worker_results)
    assert len(agg.conflicts) == 1
    assert agg.conflicts[0].claims[0]["value"] == 50
    assert agg.conflicts[0].claims[1]["value"] == 60
    assert agg.conflicts[0].resolution_status == "UNRESOLVED"
    assert agg.confidence < 0.95
