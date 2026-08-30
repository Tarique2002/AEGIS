"""Unit tests for EvaluationScorer calculation, normalization, and bounds checking."""

import pytest
from app.core.errors import EvaluationValidationError
from app.evaluation.schemas import CriterionScore
from app.evaluation.scoring import EvaluationScorer


def test_scorer_perfect_scores() -> None:
    scores = [
        CriterionScore(
            criterion_id="c1", criterion_name="C1", score=1.0, weight=0.6, justification="Good"
        ),
        CriterionScore(
            criterion_id="c2", criterion_name="C2", score=1.0, weight=0.4, justification="Good"
        ),
    ]
    overall = EvaluationScorer.calculate_overall_score(scores)
    assert overall == 1.0


def test_scorer_zero_scores() -> None:
    scores = [
        CriterionScore(
            criterion_id="c1", criterion_name="C1", score=0.0, weight=0.5, justification="Failed"
        ),
        CriterionScore(
            criterion_id="c2", criterion_name="C2", score=0.0, weight=0.5, justification="Failed"
        ),
    ]
    overall = EvaluationScorer.calculate_overall_score(scores)
    assert overall == 0.0


def test_scorer_weighted_average() -> None:
    # 0.8 * 0.75 + 0.4 * 0.25 = 0.60 + 0.10 = 0.70
    scores = [
        CriterionScore(
            criterion_id="c1", criterion_name="C1", score=0.8, weight=0.75, justification="Ok"
        ),
        CriterionScore(
            criterion_id="c2", criterion_name="C2", score=0.4, weight=0.25, justification="Weak"
        ),
    ]
    overall = EvaluationScorer.calculate_overall_score(scores)
    assert pytest.approx(overall, rel=1e-3) == 0.70


def test_scorer_unnormalized_weights_auto_normalized() -> None:
    # weights 30 and 10 -> normalized 0.75 and 0.25
    scores = [
        CriterionScore(
            criterion_id="c1", criterion_name="C1", score=1.0, weight=0.30, justification="Ok"
        ),
        CriterionScore(
            criterion_id="c2", criterion_name="C2", score=0.0, weight=0.10, justification="Failed"
        ),
    ]
    overall = EvaluationScorer.calculate_overall_score(scores)
    assert overall == 0.75


def test_scorer_empty_list_error() -> None:
    with pytest.raises(EvaluationValidationError):
        EvaluationScorer.calculate_overall_score([])
