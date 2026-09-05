"""Deterministic Learning Drift Detection Engine for Phase 12 Governance."""


from app.db.models.learning import LearnedProcedureModel, TrajectoryModel
from app.learning.governance.schemas import DriftReport, DriftStatus, GovernanceConfig


class LearningDriftDetector:
    """
    Monitors running procedures for performance, quality, latency, and failure drift
    relative to established historical baselines.
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self.config = config or GovernanceConfig()

    def assess_drift(
        self,
        procedure: LearnedProcedureModel,
        recent_trajectories: list[TrajectoryModel],
        config: GovernanceConfig | None = None,
    ) -> DriftReport:
        """
        Compare trailing window execution trajectories against baseline metrics.
        """
        active_cfg = config or self.config
        issues: list[str] = []

        # 1. Baseline metrics extraction
        base_success = (
            round(procedure.success_count / float(procedure.usage_count), 4)
            if procedure.usage_count > 0
            else 1.0
        )
        base_quality = round(procedure.validation_score or 0.85, 4)
        proc_meta = procedure.procedure_metadata or {}
        base_latency = float(proc_meta.get("baseline_latency_ms", 500.0))
        base_tokens = float(proc_meta.get("baseline_tokens_used", 1000.0))

        baseline_metrics: dict[str, float] = {
            "success_rate": base_success,
            "quality_score": base_quality,
            "avg_latency_ms": base_latency,
            "avg_tokens": base_tokens,
        }

        # If insufficient trajectories for window assessment, return healthy by default
        sample_size = len(recent_trajectories)
        if sample_size == 0:
            return DriftReport(
                procedure_id=procedure.id,
                procedure_name=procedure.name,
                version=procedure.version,
                drift_status=DriftStatus.HEALTHY,
                sample_size=0,
                baseline_metrics=baseline_metrics,
                recent_metrics=baseline_metrics,
                metric_deltas={},
                detected_issues=["Insufficient execution samples for drift evaluation."],
            )

        # 2. Recent metrics aggregation
        recent_success_count = sum(1 for t in recent_trajectories if t.is_success)
        recent_success_rate = round(recent_success_count / float(sample_size), 4)

        # Quality extraction
        qualities: list[float] = []
        for t in recent_trajectories:
            summary = t.evaluation_summary or {}
            if isinstance(summary, dict) and "task_completion_quality" in summary:
                qualities.append(float(summary["task_completion_quality"]))
            else:
                qualities.append(1.0 if t.is_success else 0.0)
        recent_quality = round(sum(qualities) / float(len(qualities)), 4) if qualities else 0.0

        # Latency & tokens
        recent_latency = round(
            sum(t.duration_ms for t in recent_trajectories) / float(sample_size), 2
        )
        tokens_list = [t.tokens_used for t in recent_trajectories if t.tokens_used is not None]
        recent_tokens = (
            round(sum(tokens_list) / float(len(tokens_list)), 1) if tokens_list else base_tokens
        )

        # Failure rates & retries
        total_failures = sum(len(t.failures) for t in recent_trajectories)
        total_retries = sum(t.retries_count for t in recent_trajectories)
        failure_rate = round(total_failures / float(sample_size), 3)
        retry_rate = round(total_retries / float(sample_size), 3)

        recent_metrics: dict[str, float] = {
            "success_rate": recent_success_rate,
            "quality_score": recent_quality,
            "avg_latency_ms": recent_latency,
            "avg_tokens": recent_tokens,
            "failures_per_run": failure_rate,
            "retries_per_run": retry_rate,
        }

        # 3. Metric Deltas (positive delta indicates degradation for success/quality)
        success_drop = round(base_success - recent_success_rate, 4)
        quality_drop = round(base_quality - recent_quality, 4)
        latency_increase_ratio = round(
            (recent_latency - base_latency) / max(base_latency, 1.0), 3
        )
        token_increase_ratio = round(
            (recent_tokens - base_tokens) / max(base_tokens, 1.0), 3
        )

        metric_deltas: dict[str, float] = {
            "success_drop": success_drop,
            "quality_drop": quality_drop,
            "latency_increase_ratio": latency_increase_ratio,
            "token_increase_ratio": token_increase_ratio,
        }

        # 4. Status Determination
        status = DriftStatus.HEALTHY

        if success_drop >= active_cfg.drift_critical_threshold:
            status = DriftStatus.CRITICAL
            issues.append(
                f"Critical success degradation: -{success_drop * 100:.1f}% "
                f"(threshold: -{active_cfg.drift_critical_threshold * 100:.1f}%)"
            )
        elif quality_drop >= 0.25:
            status = DriftStatus.CRITICAL
            issues.append(f"Critical quality drop: -{quality_drop:.2f}")
        elif (
            success_drop >= active_cfg.drift_warning_threshold
            or quality_drop >= 0.12
            or latency_increase_ratio >= 1.5
        ):
            status = DriftStatus.DEGRADED
            if success_drop >= active_cfg.drift_warning_threshold:
                issues.append(f"Elevated failure rate drop: -{success_drop * 100:.1f}%")
            if quality_drop >= 0.12:
                issues.append(f"Quality score degraded: -{quality_drop:.2f}")
            if latency_increase_ratio >= 1.5:
                issues.append(f"Latency elevated by {latency_increase_ratio * 100:.0f}%")
        elif (
            success_drop > 0.04
            or quality_drop > 0.05
            or latency_increase_ratio > 0.5
            or failure_rate > 1.0
        ):
            status = DriftStatus.WARNING
            if success_drop > 0.04:
                issues.append(f"Mild success rate decline: -{success_drop * 100:.1f}%")
            if failure_rate > 1.0:
                issues.append(f"Frequent step failures observed: {failure_rate:.1f} per run")

        return DriftReport(
            procedure_id=procedure.id,
            procedure_name=procedure.name,
            version=procedure.version,
            drift_status=status,
            sample_size=sample_size,
            baseline_metrics=baseline_metrics,
            recent_metrics=recent_metrics,
            metric_deltas=metric_deltas,
            detected_issues=issues,
        )
