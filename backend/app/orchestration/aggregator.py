"""Result aggregation, semantic conflict detection, evidence ranking, and synthesis."""

import uuid
from typing import Any

from app.core.logging import get_logger
from app.orchestration.schemas import (
    AggregatedResult,
    ConflictRecord,
    ConflictResolutionMethod,
    DelegatedTaskStatus,
    OrchestrationStatus,
    WorkerResult,
)
from app.schemas.common import utc_now

logger = get_logger(__name__)


class ResultAggregator:
    """Synthesizes worker results, detects contradictions, and produces structured outcomes."""

    def aggregate(
        self,
        orchestration_id: uuid.UUID,
        worker_results: dict[str, WorkerResult],
    ) -> AggregatedResult:
        """Synthesize worker contributions, perform conflict detection, and establish provenance."""
        # 1. Separate completed vs failed/blocked
        completed_results = {
            t_id: res
            for t_id, res in worker_results.items()
            if res.status == DelegatedTaskStatus.COMPLETED
        }
        failed_results = {
            t_id: res
            for t_id, res in worker_results.items()
            if res.status != DelegatedTaskStatus.COMPLETED
        }

        # 2. Detect conflicts across completed workers
        conflicts = self._detect_conflicts(completed_results)

        # 3. Assemble provenance records
        provenance = [
            {
                "task_id": t_id,
                "worker_id": res.worker_id,
                "worker_type": res.worker_type.value,
                "status": res.status.value,
                "confidence": res.confidence,
                "duration_ms": res.duration_ms,
            }
            for t_id, res in worker_results.items()
        ]

        # 4. Synthesize final output
        contributions = {t_id: res.result for t_id, res in completed_results.items()}

        if not completed_results:
            status = OrchestrationStatus.FAILED
            summary = "All worker tasks failed or were blocked."
            final_output = None
            confidence = 0.0
        elif failed_results:
            status = OrchestrationStatus.PARTIAL
            summary = (
                f"Orchestration completed with partial results: "
                f"{len(completed_results)} succeeded, {len(failed_results)} failed."
            )
            final_output = self._synthesize_output(completed_results)
            confidence = 0.6 if not conflicts else 0.4
        else:
            status = OrchestrationStatus.COMPLETED
            summary = f"All {len(completed_results)} worker tasks completed successfully."
            final_output = self._synthesize_output(completed_results)
            confidence = 0.95 if not conflicts else 0.7

        return AggregatedResult(
            orchestration_id=orchestration_id,
            status=status,
            final_output=final_output,
            summary=summary,
            worker_contributions=contributions,
            conflicts=conflicts,
            confidence=confidence,
            provenance=provenance,
            created_at=utc_now(),
        )

    def _detect_conflicts(self, completed_results: dict[str, WorkerResult]) -> list[ConflictRecord]:
        """Detect disagreements in numerical results or contradictory claims."""
        conflicts: list[ConflictRecord] = []
        numeric_claims: dict[str, list[tuple[str, str, Any]]] = {}

        for t_id, res in completed_results.items():
            if isinstance(res.result, int | float):
                key = "numeric_scalar"
                numeric_claims.setdefault(key, []).append((t_id, res.worker_id, res.result))
            elif isinstance(res.result, dict):
                for k, v in res.result.items():
                    if isinstance(v, int | float | str):
                        numeric_claims.setdefault(k, []).append((t_id, res.worker_id, v))

        for claim_key, items in numeric_claims.items():
            if len(items) > 1:
                # Check if values differ across distinct workers
                unique_vals = {item[2] for item in items}
                if len(unique_vals) > 1:
                    logger.warning(f"Detected conflict on key '{claim_key}': values {unique_vals}")
                    conflicts.append(
                        ConflictRecord(
                            worker_ids=list({item[1] for item in items}),
                            task_ids=list({item[0] for item in items}),
                            claims=[
                                {"task_id": item[0], "worker_id": item[1], "value": item[2]}
                                for item in items
                            ],
                            severity="HIGH" if len(unique_vals) > 2 else "MEDIUM",
                            resolution_status="UNRESOLVED",
                            resolution_method=ConflictResolutionMethod.EVIDENCE_PRIORITY,
                            resolution_notes=(
                                f"Conflicting values detected for '{claim_key}': {unique_vals}"
                            ),
                        )
                    )

        return conflicts

    def _synthesize_output(self, completed_results: dict[str, WorkerResult]) -> Any:
        """Derive final output structure from worker outputs (preferring synthesis)."""
        # Look for synthesis worker task output first
        for res in completed_results.values():
            if res.worker_type.value == "SYNTHESIS" and res.result is not None:
                return res.result

        # Otherwise, bundle all contributions
        return {t_id: res.result for t_id, res in completed_results.items()}
