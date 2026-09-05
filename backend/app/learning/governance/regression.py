"""Deterministic Regression & Shadow Evaluation Engine for Phase 12 Governance."""

import uuid
from typing import Any

from app.db.models.learning import LearnedProcedureModel, TrajectoryModel
from app.learning.governance.schemas import GovernanceConfig, ShadowEvaluationResult


class ProcedureRegressionEvaluator:
    """
    Evaluates candidate procedures against baseline production strategies using
    historical execution trajectories without mutating live production state.
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self.config = config or GovernanceConfig()

    def evaluate_shadow(
        self,
        candidate: LearnedProcedureModel,
        baseline: LearnedProcedureModel | None,
        trajectories: list[TrajectoryModel],
        config: GovernanceConfig | None = None,
    ) -> ShadowEvaluationResult:
        """
        Execute deterministic shadow comparison between candidate and baseline strategy.
        """
        active_cfg = config or self.config
        reasons: list[str] = []

        # 1. Candidate metrics derivation
        cand_tools = set(candidate.required_tools or [])
        cand_steps_count = len(candidate.ordered_steps or [])

        # Replay feasibility over representative sample trajectories
        compatible_sample_count = 0
        total_sample = len(trajectories) or 1

        for traj in trajectories:
            traj_tools = set(traj.selected_tools or [])
            # If candidate requires tools that are completely alien to domain, note penalty
            if cand_tools.issubset(traj_tools) or not cand_tools:
                compatible_sample_count += 1

        feasibility_ratio = round(compatible_sample_count / float(total_sample), 3)

        cand_quality = round(candidate.validation_score or candidate.confidence, 4)
        cand_efficiency = round(1.0 / max(cand_steps_count, 1), 3)

        candidate_metrics: dict[str, Any] = {
            "validation_score": cand_quality,
            "confidence": candidate.confidence,
            "steps_count": cand_steps_count,
            "step_efficiency": cand_efficiency,
            "tool_feasibility_rate": feasibility_ratio,
            "sample_size": len(trajectories),
        }

        # 2. Baseline metrics derivation
        if baseline:
            base_steps_count = len(baseline.ordered_steps or [])
            base_quality = round(baseline.validation_score or baseline.confidence, 4)
            base_efficiency = round(1.0 / max(base_steps_count, 1), 3)

            baseline_metrics: dict[str, Any] = {
                "validation_score": base_quality,
                "confidence": baseline.confidence,
                "steps_count": base_steps_count,
                "step_efficiency": base_efficiency,
                "sample_size": len(trajectories),
            }


            # 3. Metric deltas (candidate - baseline)
            quality_delta = round(cand_quality - base_quality, 4)
            step_delta = cand_steps_count - base_steps_count

            # Regression detected if quality drops below tolerance
            regression_detected = quality_delta < -active_cfg.max_regression_tolerance
            if regression_detected:
                reasons.append(
                    f"Quality regression detected: {quality_delta:.4f} < "
                    f"-{active_cfg.max_regression_tolerance:.4f} tolerance limit."
                )

            if cand_steps_count > base_steps_count * 2 and cand_steps_count > 6:
                reasons.append(
                    f"Candidate introduces excessive step complexity: {cand_steps_count} "
                    f"vs baseline {base_steps_count}."
                )

            promotion_recommended = (not regression_detected) and (
                cand_quality >= active_cfg.min_quality_score
            )
            if promotion_recommended:
                reasons.append("Candidate demonstrates equal or superior performance to baseline.")
        else:
            # First version (no prior baseline)
            baseline_metrics = {}
            quality_delta = 0.0
            step_delta = 0
            regression_detected = False
            promotion_recommended = cand_quality >= active_cfg.min_quality_score
            reasons.append("No baseline strategy exists; candidate evaluated as initial baseline.")

        metric_deltas: dict[str, Any] = {
            "quality_delta": quality_delta,
            "step_delta": step_delta,
            "feasibility_ratio": feasibility_ratio,
        }

        return ShadowEvaluationResult(
            evaluation_id=uuid.uuid4(),
            baseline_procedure_id=baseline.id if baseline else None,
            candidate_procedure_id=candidate.id,
            evaluation_type="SHADOW",
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            metric_deltas=metric_deltas,
            regression_detected=regression_detected,
            promotion_recommended=promotion_recommended,
            reasons=reasons,
            status="COMPLETED",
        )
