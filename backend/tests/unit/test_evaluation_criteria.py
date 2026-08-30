"""Unit tests for evaluation criteria catalog, filtering, and normalization."""

import pytest
from app.core.errors import EvaluationValidationError
from app.evaluation.criteria import (
    filter_criteria,
    get_default_criteria,
    validate_and_normalize_weights,
)
from app.evaluation.schemas import EvaluationCriterion, EvaluationType


def test_default_criteria_weights_total_one() -> None:
    criteria = get_default_criteria()
    assert len(criteria) == 6
    total_weight = sum(c.weight for c in criteria)
    assert pytest.approx(total_weight, rel=1e-4) == 1.0


def test_validate_and_normalize_weights_proportional() -> None:
    custom = [
        EvaluationCriterion(
            criterion_id="c1",
            name="C1",
            description="C1",
            weight=0.5,
            enabled=True,
            evaluation_type=EvaluationType.CORRECTNESS,
        ),
        EvaluationCriterion(
            criterion_id="c2",
            name="C2",
            description="C2",
            weight=0.5,
            enabled=True,
            evaluation_type=EvaluationType.SAFETY,
        ),
    ]
    normalized = validate_and_normalize_weights(custom)
    assert len(normalized) == 2
    assert normalized[0].weight == 0.5
    assert normalized[1].weight == 0.5
    assert sum(c.weight for c in normalized) == 1.0


def test_validate_and_normalize_weights_with_disabled() -> None:
    custom = [
        EvaluationCriterion(
            criterion_id="c1",
            name="C1",
            description="C1",
            weight=0.4,
            enabled=True,
            evaluation_type=EvaluationType.CORRECTNESS,
        ),
        EvaluationCriterion(
            criterion_id="c2",
            name="C2",
            description="C2",
            weight=0.6,
            enabled=False,  # Disabled
            evaluation_type=EvaluationType.EFFICIENCY,
        ),
    ]
    normalized = validate_and_normalize_weights(custom)
    assert normalized[0].weight == 1.0  # Normalized to 1.0
    assert normalized[1].weight == 0.0


def test_validate_and_normalize_weights_empty_error() -> None:
    with pytest.raises(EvaluationValidationError):
        validate_and_normalize_weights([])


def test_validate_and_normalize_weights_all_disabled_error() -> None:
    custom = [
        EvaluationCriterion(
            criterion_id="c1",
            name="C1",
            description="C1",
            weight=0.5,
            enabled=False,
            evaluation_type=EvaluationType.CORRECTNESS,
        )
    ]
    with pytest.raises(EvaluationValidationError):
        validate_and_normalize_weights(custom)


def test_filter_criteria() -> None:
    criteria = get_default_criteria()
    filtered = filter_criteria(criteria, criterion_ids=["correctness", "safety"])
    assert len(filtered) == 2
    ids = [c.criterion_id for c in filtered]
    assert "correctness" in ids
    assert "safety" in ids
