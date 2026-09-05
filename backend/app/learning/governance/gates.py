"""Deterministic Promotion Gate Engine for Phase 12 Learning Governance."""

from app.db.models.learning import LearnedProcedureModel
from app.learning.governance.schemas import (
    ApprovalStatus,
    GateCheckResult,
    GovernanceConfig,
    GovernanceProcedureStatus,
    PromotionGateResult,
    SafetyClassification,
)


class DeterministicPromotionGateEngine:
    """
    Evaluates learned procedures against multi-dimensional deterministic promotion gates.
    Prevents silent, LLM-only, or unsafe promotions into production.
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self.config = config or GovernanceConfig()

    def evaluate_gates(
        self,
        procedure: LearnedProcedureModel,
        config: GovernanceConfig | None = None,
        regression_delta: float | None = None,
    ) -> PromotionGateResult:
        """
        Deterministically evaluate all promotion criteria against configured thresholds.
        """
        active_cfg = config or self.config
        checks: list[GateCheckResult] = []

        # 1. Evaluation Count Gate
        eval_count = len(procedure.source_evaluation_ids) or procedure.usage_count
        eval_passed = eval_count >= active_cfg.min_evaluation_count
        checks.append(
            GateCheckResult(
                rule_name="min_evaluation_count",
                passed=eval_passed,
                actual_value=eval_count,
                expected_threshold=active_cfg.min_evaluation_count,
                detail=(
                    f"Evaluations count {eval_count} >= required {active_cfg.min_evaluation_count}"
                    if eval_passed
                    else f"Evaluations {eval_count} < {active_cfg.min_evaluation_count}"
                ),
            )
        )


        # 2. Success Rate Gate
        total_runs = procedure.usage_count
        if total_runs > 0:
            success_rate = round(procedure.success_count / float(total_runs), 4)
        else:
            # Fallback for new candidates with zero usage count
            success_rate = 1.0 if procedure.success_count > 0 else 0.0

        success_passed = success_rate >= active_cfg.min_success_rate
        checks.append(
            GateCheckResult(
                rule_name="min_success_rate",
                passed=success_passed,
                actual_value=success_rate,
                expected_threshold=active_cfg.min_success_rate,
                detail=(
                    f"Success rate {success_rate:.2f} >= required {active_cfg.min_success_rate:.2f}"
                    if success_passed
                    else f"Success rate {success_rate:.2f} below {active_cfg.min_success_rate:.2f}"
                ),
            )
        )

        # 3. Quality / Validation Score Gate
        quality_score = round(procedure.validation_score, 4)
        quality_passed = quality_score >= active_cfg.min_quality_score
        checks.append(
            GateCheckResult(
                rule_name="min_quality_score",
                passed=quality_passed,
                actual_value=quality_score,
                expected_threshold=active_cfg.min_quality_score,
                detail=(
                    f"Validation quality {quality_score:.2f} >= "
                    f"required {active_cfg.min_quality_score:.2f}"
                    if quality_passed
                    else f"Quality score {quality_score:.2f} < {active_cfg.min_quality_score:.2f}"
                ),
            )
        )

        # 4. Confidence Gate
        confidence = round(procedure.confidence, 4)
        confidence_passed = confidence >= active_cfg.min_confidence
        checks.append(
            GateCheckResult(
                rule_name="min_confidence",
                passed=confidence_passed,
                actual_value=confidence,
                expected_threshold=active_cfg.min_confidence,
                detail=(
                    f"Confidence {confidence:.2f} >= required {active_cfg.min_confidence:.2f}"
                    if confidence_passed
                    else f"Confidence {confidence:.2f} < {active_cfg.min_confidence:.2f}"
                ),
            )
        )

        # 5. Safety & Policy Violations Gate
        metadata = procedure.provenance_metadata or {}
        safety_violations = metadata.get("safety_violations", 0)
        policy_violations = metadata.get("policy_violations", 0)
        safety_passed = (safety_violations == 0) and (policy_violations == 0)
        checks.append(
            GateCheckResult(
                rule_name="zero_safety_policy_violations",
                passed=safety_passed,
                actual_value={"safety": safety_violations, "policy": policy_violations},
                expected_threshold={"safety": 0, "policy": 0},
                detail=(
                    "Zero safety and policy violations verified"
                    if safety_passed
                    else f"Violations: safety={safety_violations}, policy={policy_violations}"
                ),
            )
        )


        # 6. Regression Tolerance Gate
        regression_passed = True
        if regression_delta is not None:
            regression_passed = regression_delta <= active_cfg.max_regression_tolerance
            checks.append(
                GateCheckResult(
                    rule_name="regression_tolerance",
                    passed=regression_passed,
                    actual_value=round(regression_delta, 4),
                    expected_threshold=active_cfg.max_regression_tolerance,
                    detail=(
                        f"Regression delta {regression_delta:.4f} <= "
                        f"tolerance {active_cfg.max_regression_tolerance:.4f}"
                        if regression_passed
                        else f"Excessive regression {regression_delta:.4f} > "
                        f"tolerance {active_cfg.max_regression_tolerance:.4f}"
                    ),
                )
            )

        # 7. Human Oversight Gate for High-Risk Procedures
        classification = procedure.safety_classification or SafetyClassification.LOW.value
        is_high_risk = classification in (
            SafetyClassification.HIGH.value,
            SafetyClassification.CRITICAL.value,
        )
        requires_approval = is_high_risk and active_cfg.require_human_approval_for_high_risk
        is_approved = procedure.approval_status == ApprovalStatus.APPROVED.value
        blocked_by_approval = requires_approval and not is_approved

        checks.append(
            GateCheckResult(
                rule_name="human_approval_gate",
                passed=not blocked_by_approval,
                actual_value=procedure.approval_status,
                expected_threshold="APPROVED" if requires_approval else "NOT_REQUIRED",
                detail=(
                    "Human approval granted or not required"
                    if not blocked_by_approval
                    else f"Explicit human approval required for {classification} risk procedure"
                ),
            )
        )

        # Overall gate decision
        failed_checks = [c for c in checks if not c.passed]
        all_passed = len(failed_checks) == 0

        if all_passed:
            status = GovernanceProcedureStatus.PROMOTED
            reason = "All deterministic promotion gates and validation checks satisfied."
        elif blocked_by_approval and len(failed_checks) == 1:
            status = GovernanceProcedureStatus.PENDING_APPROVAL
            reason = (
                f"Automated gates passed; awaiting human approval for {classification} procedure."
            )
        else:
            status = GovernanceProcedureStatus.REJECTED
            reasons = [f"{c.rule_name}: {c.detail}" for c in failed_checks]
            reason = "; ".join(reasons)

        return PromotionGateResult(
            passed=all_passed,
            status=status,
            checks=checks,
            reason=reason,
            requires_human_approval=requires_approval,
            is_blocked_by_approval=blocked_by_approval,
        )
