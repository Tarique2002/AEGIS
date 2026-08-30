"""Worker result collection, validation, failure tracking, and provenance correlation."""

from typing import Any

from app.core.logging import get_logger
from app.orchestration.schemas import (
    DelegatedTaskStatus,
    DelegationPlan,
    WorkerResult,
)

logger = get_logger(__name__)


class WorkerResultCollector:
    """Collects, validates, and normalizes execution results from all dispatched worker agents."""

    @staticmethod
    def collect_and_validate(
        plan: DelegationPlan,
        raw_results: dict[str, WorkerResult],
    ) -> dict[str, WorkerResult]:
        """
        Validate all worker results against plan tasks, ensuring completeness and normalization.
        """
        validated_results: dict[str, WorkerResult] = {}

        for task in plan.tasks:
            t_id = task.delegated_task_id
            if t_id not in raw_results:
                logger.warning(
                    f"Missing worker result for delegated task '{t_id}'. Recording as FAILED."
                )
                validated_results[t_id] = WorkerResult(
                    worker_id=task.worker_id,
                    delegated_task_id=t_id,
                    worker_type=task.worker_type,
                    status=DelegatedTaskStatus.FAILED,
                    result=None,
                    confidence=0.0,
                    execution_summary="Result missing from worker execution.",
                    error="Missing worker result. Worker result was not returned.",
                )
            else:
                res = raw_results[t_id]
                # Normalize result fields
                if res.confidence < 0.0 or res.confidence > 1.0:
                    res.confidence = max(0.0, min(1.0, res.confidence))
                validated_results[t_id] = res

        return validated_results

    @staticmethod
    def extract_successful_contributions(
        results: dict[str, WorkerResult],
    ) -> dict[str, Any]:
        """Extract valid output payloads from all completed worker tasks."""
        return {
            t_id: res.result
            for t_id, res in results.items()
            if res.status == DelegatedTaskStatus.COMPLETED and res.result is not None
        }
