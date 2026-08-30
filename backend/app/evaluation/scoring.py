"""Evaluation scoring engine computing deterministic normalized weighted scores."""

from app.core.errors import EvaluationValidationError
from app.evaluation.schemas import CriterionScore


class EvaluationScorer:
    """
    Deterministic score aggregation engine.
    Calculates overall score from weighted criterion scores:
        overall_score = sum(score_i * normalized_weight_i)
    Strictly maintains 0.0 <= score <= 1.0.
    """

    @staticmethod
    def calculate_overall_score(criterion_scores: list[CriterionScore]) -> float:
        """
        Compute normalized weighted overall score across evaluated criteria.
        Raises EvaluationValidationError on empty score list or invalid numbers.
        """
        if not criterion_scores:
            raise EvaluationValidationError(
                "Cannot calculate overall score from an empty criterion scores list."
            )

        total_weight = sum(cs.weight for cs in criterion_scores)
        if total_weight <= 0.0:
            # If all weights are 0, perform simple arithmetic mean
            mean_score = sum(cs.score for cs in criterion_scores) / len(criterion_scores)
            return round(max(0.0, min(1.0, mean_score)), 4)

        weighted_sum = 0.0
        for cs in criterion_scores:
            if not (0.0 <= cs.score <= 1.0):
                raise EvaluationValidationError(
                    f"Criterion '{cs.criterion_id}' score {cs.score} out of bounds [0.0, 1.0]."
                )
            normalized_weight = cs.weight / total_weight
            weighted_sum += cs.score * normalized_weight

        # Clamp strictly to [0.0, 1.0] and round to 4 decimal places
        clamped_score = max(0.0, min(1.0, weighted_sum))
        return round(clamped_score, 4)
