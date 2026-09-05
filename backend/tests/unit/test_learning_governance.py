"""Unit tests for Phase 12 Production Learning Governance Engine."""

import uuid

from app.db.models.learning import LearnedProcedureModel, TrajectoryModel
from app.learning.governance.drift import LearningDriftDetector
from app.learning.governance.gates import DeterministicPromotionGateEngine
from app.learning.governance.regression import ProcedureRegressionEvaluator
from app.learning.governance.schemas import (
    ApprovalStatus,
    DriftStatus,
    GovernanceConfig,
    GovernanceProcedureStatus,
    SafetyClassification,
)


def _build_procedure(
    user_id: uuid.UUID | None = None,
    name: str = "Test Strategy",
    confidence: float = 0.90,
    validation_score: float = 0.88,
    usage_count: int = 5,
    success_count: int = 5,
    failure_count: int = 0,
    classification: str = "LOW",
    approval_status: str = "NONE",
    safety_violations: int = 0,
    policy_violations: int = 0,
    tools: list[str] | None = None,
    steps: list[dict] | None = None,
) -> LearnedProcedureModel:
    return LearnedProcedureModel(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        task_domain="analytics",
        name=name,
        description="Strategy for testing governance gates",
        trigger_conditions=["objective_matches: test"],
        ordered_steps=steps or [{"step": 1, "tool": "data_tool", "action": "query"}],
        required_tools=tools or ["data_tool"],
        constraints=["tenant_isolation"],
        success_criteria=["zero_errors"],
        confidence=confidence,
        usage_count=usage_count,
        success_count=success_count,
        failure_count=failure_count,
        version=1,
        status="CANDIDATE",
        is_global=False,
        source_trajectory_ids=[str(uuid.uuid4()) for _ in range(usage_count)],
        source_evaluation_ids=[str(uuid.uuid4()) for _ in range(usage_count)],
        validation_score=validation_score,
        safety_classification=classification,
        approval_status=approval_status,
        provenance_metadata={
            "safety_violations": safety_violations,
            "policy_violations": policy_violations,
            "baseline_latency_ms": 250.0,
            "baseline_tokens_used": 600.0,
        },
        procedure_metadata={"baseline_latency_ms": 250.0, "baseline_tokens_used": 600.0},
    )


def test_promotion_gate_passed_when_thresholds_satisfied() -> None:
    engine = DeterministicPromotionGateEngine()
    proc = _build_procedure(confidence=0.92, validation_score=0.90, usage_count=4, success_count=4)

    result = engine.evaluate_gates(proc)
    assert result.passed is True
    assert result.status == GovernanceProcedureStatus.PROMOTED
    assert result.is_blocked_by_approval is False
    assert len(result.checks) >= 6


def test_promotion_gate_rejected_when_quality_low() -> None:
    engine = DeterministicPromotionGateEngine()
    proc = _build_procedure(validation_score=0.65)  # threshold is 0.80

    result = engine.evaluate_gates(proc)
    assert result.passed is False
    assert result.status == GovernanceProcedureStatus.REJECTED
    assert any(c.rule_name == "min_quality_score" and not c.passed for c in result.checks)


def test_promotion_gate_rejected_when_evaluations_insufficient() -> None:
    engine = DeterministicPromotionGateEngine()
    proc = _build_procedure(usage_count=1, success_count=1)
    proc.source_evaluation_ids = [str(uuid.uuid4())]  # threshold is 3

    result = engine.evaluate_gates(proc)
    assert result.passed is False
    assert any(c.rule_name == "min_evaluation_count" and not c.passed for c in result.checks)


def test_promotion_gate_blocks_high_risk_without_human_approval() -> None:
    engine = DeterministicPromotionGateEngine()
    proc = _build_procedure(
        confidence=0.95,
        validation_score=0.92,
        classification=SafetyClassification.HIGH.value,
        approval_status=ApprovalStatus.NONE.value,
    )

    result = engine.evaluate_gates(proc)
    assert result.passed is False
    assert result.requires_human_approval is True
    assert result.is_blocked_by_approval is True
    assert result.status == GovernanceProcedureStatus.PENDING_APPROVAL


def test_promotion_gate_allows_high_risk_with_human_approval() -> None:
    engine = DeterministicPromotionGateEngine()
    proc = _build_procedure(
        confidence=0.95,
        validation_score=0.92,
        classification=SafetyClassification.HIGH.value,
        approval_status=ApprovalStatus.APPROVED.value,
    )

    result = engine.evaluate_gates(proc)
    assert result.passed is True
    assert result.status == GovernanceProcedureStatus.PROMOTED
    assert result.is_blocked_by_approval is False


def test_promotion_gate_rejects_safety_violations() -> None:
    engine = DeterministicPromotionGateEngine()
    proc = _build_procedure(safety_violations=2)

    result = engine.evaluate_gates(proc)
    assert result.passed is False
    assert result.status == GovernanceProcedureStatus.REJECTED
    assert any(
        c.rule_name == "zero_safety_policy_violations" and not c.passed
        for c in result.checks
    )



def test_llm_cannot_directly_promote() -> None:
    """Security Invariant: Even if an LLM marks confidence=1.0, failing gates blocks promotion."""
    engine = DeterministicPromotionGateEngine()
    # High LLM confidence but zero recorded successful evaluations
    proc = _build_procedure(confidence=1.0, validation_score=0.20, usage_count=0, success_count=0)
    proc.source_evaluation_ids = []

    result = engine.evaluate_gates(proc)
    assert result.passed is False
    assert result.status != GovernanceProcedureStatus.PROMOTED


def test_drift_detector_healthy() -> None:
    detector = LearningDriftDetector()
    proc = _build_procedure(usage_count=10, success_count=10, validation_score=0.90)

    # 5 healthy recent runs
    trajs = [
        TrajectoryModel(
            id=uuid.uuid4(),
            user_id=proc.user_id,
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            goal="Test query",
            selected_tools=["data_tool"],
            is_success=True,
            duration_ms=240.0,
            tokens_used=580,
            failures=[],
            retries_count=0,
            evaluation_summary={"task_completion_quality": 0.92},
        )
        for _ in range(5)
    ]

    report = detector.assess_drift(proc, trajs)
    assert report.drift_status == DriftStatus.HEALTHY
    assert report.sample_size == 5
    assert len(report.detected_issues) == 0


def test_drift_detector_detects_degradation() -> None:
    detector = LearningDriftDetector()
    proc = _build_procedure(usage_count=10, success_count=10, validation_score=0.90)

    # Trailing runs with elevated failure rate and high latency
    trajs = [
        TrajectoryModel(
            id=uuid.uuid4(),
            user_id=proc.user_id,
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            goal="Degraded query",
            selected_tools=["data_tool"],
            is_success=(i % 2 == 0),
            duration_ms=800.0,  # Elevated from 250 baseline
            tokens_used=600,
            failures=[{"error": "tool timeout"}],
            retries_count=1,
            evaluation_summary={"task_completion_quality": 0.65},
        )
        for i in range(6)
    ]

    report = detector.assess_drift(proc, trajs)
    assert report.drift_status in (DriftStatus.DEGRADED, DriftStatus.CRITICAL)
    assert len(report.detected_issues) > 0


def test_shadow_evaluation_no_baseline() -> None:
    evaluator = ProcedureRegressionEvaluator()
    candidate = _build_procedure(confidence=0.88, validation_score=0.86)

    trajs = [
        TrajectoryModel(
            id=uuid.uuid4(),
            user_id=candidate.user_id,
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            goal="Shadow query",
            selected_tools=["data_tool"],
            is_success=True,
            duration_ms=200.0,
        )
    ]

    res = evaluator.evaluate_shadow(candidate=candidate, baseline=None, trajectories=trajs)
    assert res.regression_detected is False
    assert res.promotion_recommended is True
    assert res.baseline_procedure_id is None


def test_shadow_evaluation_detects_regression() -> None:
    evaluator = ProcedureRegressionEvaluator()
    baseline = _build_procedure(name="Baseline Strategy", validation_score=0.92)
    # Candidate with significantly degraded validation score
    candidate = _build_procedure(name="Regression Candidate", validation_score=0.70)

    cfg = GovernanceConfig(max_regression_tolerance=0.05)
    res = evaluator.evaluate_shadow(
        candidate=candidate,
        baseline=baseline,
        trajectories=[],
        config=cfg,
    )
    assert res.regression_detected is True
    assert res.promotion_recommended is False
    assert res.metric_deltas["quality_delta"] < -0.05
