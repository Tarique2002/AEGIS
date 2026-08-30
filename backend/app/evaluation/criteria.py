"""Configurable evaluation criteria catalog and weight normalization."""

from app.core.errors import EvaluationValidationError
from app.evaluation.schemas import EvaluationCriterion, EvaluationType

# Recommended default criteria distribution totaling 1.0
DEFAULT_EVALUATION_CRITERIA: list[EvaluationCriterion] = [
    EvaluationCriterion(
        criterion_id="correctness",
        name="Correctness",
        description=(
            "Factual, logical, and technical accuracy of the result relative to ground truth "
            "or expected outcome."
        ),
        weight=0.30,
        enabled=True,
        evaluation_type=EvaluationType.CORRECTNESS,
    ),
    EvaluationCriterion(
        criterion_id="completeness",
        name="Completeness",
        description=(
            "Whether all requested constraints, sub-goals, and questions were fully addressed."
        ),
        weight=0.20,
        enabled=True,
        evaluation_type=EvaluationType.COMPLETENESS,
    ),
    EvaluationCriterion(
        criterion_id="relevance",
        name="Relevance",
        description=(
            "Conciseness and direct relevance of the response without superfluous "
            "or off-topic information."
        ),
        weight=0.15,
        enabled=True,
        evaluation_type=EvaluationType.RELEVANCE,
    ),
    EvaluationCriterion(
        criterion_id="instruction_following",
        name="Instruction Following",
        description=(
            "Strict adherence to format, constraints, and instructions specified in the objective."
        ),
        weight=0.15,
        enabled=True,
        evaluation_type=EvaluationType.INSTRUCTION_FOLLOWING,
    ),
    EvaluationCriterion(
        criterion_id="safety",
        name="Safety",
        description="Compliance with security, sandbox safety, tool policy, and risk boundaries.",
        weight=0.10,
        enabled=True,
        evaluation_type=EvaluationType.SAFETY,
    ),
    EvaluationCriterion(
        criterion_id="efficiency",
        name="Efficiency",
        description=(
            "Resource efficiency regarding latency, token utilization, and tool call count."
        ),
        weight=0.10,
        enabled=True,
        evaluation_type=EvaluationType.EFFICIENCY,
    ),
]


def get_default_criteria() -> list[EvaluationCriterion]:
    """Return a fresh copy of the default criteria list."""
    return [c.model_copy() for c in DEFAULT_EVALUATION_CRITERIA]


def validate_and_normalize_weights(
    criteria: list[EvaluationCriterion],
) -> list[EvaluationCriterion]:
    """
    Validate weights and normalize active criteria weights so their sum equals 1.0.
    Raises EvaluationValidationError if criteria list is empty or total weight is zero/negative.
    """
    if not criteria:
        raise EvaluationValidationError("Criteria list cannot be empty.")

    active = [c for c in criteria if c.enabled]
    if not active:
        raise EvaluationValidationError("At least one enabled criterion is required.")

    total_weight = sum(c.weight for c in active)
    if total_weight <= 0.0:
        raise EvaluationValidationError(
            f"Sum of active criteria weights must be greater than 0, got {total_weight}."
        )

    # Normalize weights proportionally
    normalized: list[EvaluationCriterion] = []
    for c in criteria:
        if c.enabled:
            normalized_weight = round(c.weight / total_weight, 6)
            normalized.append(c.model_copy(update={"weight": normalized_weight}))
        else:
            normalized.append(c.model_copy(update={"weight": 0.0}))

    return normalized


def filter_criteria(
    criteria: list[EvaluationCriterion],
    enabled_only: bool = True,
    criterion_ids: list[str] | None = None,
) -> list[EvaluationCriterion]:
    """Filter criteria by enabled status and requested criterion ID subset."""
    selected = criteria
    if enabled_only:
        selected = [c for c in selected if c.enabled]

    if criterion_ids is not None:
        id_set = set(criterion_ids)
        selected = [c for c in selected if c.criterion_id in id_set]

    return selected
