"""Unit tests for Evaluation & Reflection schemas and validation constraints."""

import uuid

import pytest
from app.evaluation.schemas import (
    CriterionScore,
    EvaluationCriterion,
    EvaluationResult,
    EvaluationType,
    FailureCategory,
    ReflectionRecord,
    RootCauseCategory,
)
from pydantic import ValidationError


def test_evaluation_criterion_valid() -> None:
    criterion = EvaluationCriterion(
        criterion_id="correctness",
        name="Correctness",
        description="Factual and logical correctness.",
        weight=0.35,
        enabled=True,
        evaluation_type=EvaluationType.CORRECTNESS,
    )
    assert criterion.criterion_id == "correctness"
    assert criterion.weight == 0.35
    assert criterion.enabled is True


def test_evaluation_criterion_invalid_weight() -> None:
    with pytest.raises(ValidationError):
        EvaluationCriterion(
            criterion_id="invalid",
            name="Invalid",
            description="Test",
            weight=1.5,  # Must be <= 1.0
            evaluation_type=EvaluationType.SAFETY,
        )

    with pytest.raises(ValidationError):
        EvaluationCriterion(
            criterion_id="invalid",
            name="Invalid",
            description="Test",
            weight=-0.1,  # Must be >= 0.0
            evaluation_type=EvaluationType.SAFETY,
        )


def test_criterion_score_validation() -> None:
    score = CriterionScore(
        criterion_id="safety",
        criterion_name="Safety",
        score=0.95,
        weight=0.10,
        justification="No safety violations observed.",
        evidence={"violations": 0},
    )
    assert score.score == 0.95
    assert score.weight == 0.10

    # Test out of bounds score
    with pytest.raises(ValidationError):
        CriterionScore(
            criterion_id="safety",
            criterion_name="Safety",
            score=1.05,
            weight=0.10,
            justification="Invalid",
        )

    with pytest.raises(ValidationError):
        CriterionScore(
            criterion_id="safety",
            criterion_name="Safety",
            score=-0.1,
            weight=0.10,
            justification="Invalid",
        )


def test_evaluation_result_schema() -> None:
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    result = EvaluationResult(
        task_id=task_id,
        run_id=run_id,
        overall_score=0.88,
        criterion_scores=[
            CriterionScore(
                criterion_id="correctness",
                criterion_name="Correctness",
                score=0.9,
                weight=0.5,
                justification="Accurate",
            )
        ],
        passed=True,
        failure_categories=[FailureCategory.NONE],
        strengths=["High accuracy"],
        weaknesses=[],
        recommendations=["Keep up good performance"],
    )
    assert result.overall_score == 0.88
    assert result.passed is True
    assert result.failure_categories == [FailureCategory.NONE]


def test_evaluation_result_default_failure_category() -> None:
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    result = EvaluationResult(
        task_id=task_id,
        run_id=run_id,
        overall_score=0.9,
        criterion_scores=[],
        passed=True,
        failure_categories=[],  # Empty list should default to [FailureCategory.NONE]
    )
    assert result.failure_categories == [FailureCategory.NONE]


def test_reflection_record_schema() -> None:
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    record = ReflectionRecord(
        task_id=task_id,
        run_id=run_id,
        evaluation_id=eval_id,
        summary="Run succeeded with optimal tool calls.",
        what_went_well=["Executed calculator tool cleanly"],
        what_went_wrong=[],
        root_causes=[],
        improvement_suggestions=["No adjustments necessary"],
        confidence=0.95,
    )
    assert record.confidence == 0.95
    assert record.task_id == task_id
    assert record.evaluation_id == eval_id


def test_reflection_record_confidence_bounds() -> None:
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        ReflectionRecord(
            task_id=task_id,
            run_id=run_id,
            evaluation_id=eval_id,
            summary="Invalid",
            confidence=1.2,
        )


def test_failure_and_root_cause_taxonomies() -> None:
    assert FailureCategory.TIMEOUT.value == "TIMEOUT"
    assert FailureCategory.POLICY_VIOLATION.value == "POLICY_VIOLATION"
    assert FailureCategory.TOOL_FAILURE.value == "TOOL_FAILURE"

    assert RootCauseCategory.TOOL_FAILURE.value == "tool_failure"
    assert RootCauseCategory.POLICY_CONSTRAINT.value == "policy_constraint"
    assert RootCauseCategory.UNKNOWN.value == "unknown"
