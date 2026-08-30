"""AEGIS Autonomous Agent Evaluation & Reflection Subsystem (Phase 4)."""

from app.evaluation.criteria import (
    filter_criteria,
    get_default_criteria,
    validate_and_normalize_weights,
)
from app.evaluation.errors import (
    EvaluationError,
    EvaluationExecutionError,
    EvaluationNotFoundError,
    EvaluationPolicyViolationError,
    EvaluationValidationError,
    ReflectionError,
    ReflectionValidationError,
)
from app.evaluation.evaluator import DeterministicEvaluator, EvaluationEngine, LLMEvaluator
from app.evaluation.policies import EvaluationPolicy
from app.evaluation.reflection import ReflectionEngine
from app.evaluation.repository import EvaluationRepository
from app.evaluation.schemas import (
    CriterionScore,
    EvaluationCriterion,
    EvaluationRequest,
    EvaluationResult,
    EvaluationType,
    FailureCategory,
    ReflectionRecord,
    ReflectionRequest,
    RootCauseCategory,
)
from app.evaluation.scoring import EvaluationScorer
from app.evaluation.service import EvaluationService

__all__ = [
    "EvaluationType",
    "FailureCategory",
    "RootCauseCategory",
    "EvaluationCriterion",
    "CriterionScore",
    "EvaluationRequest",
    "EvaluationResult",
    "ReflectionRequest",
    "ReflectionRecord",
    "EvaluationError",
    "EvaluationNotFoundError",
    "EvaluationValidationError",
    "EvaluationPolicyViolationError",
    "EvaluationExecutionError",
    "ReflectionError",
    "ReflectionValidationError",
    "EvaluationPolicy",
    "EvaluationScorer",
    "get_default_criteria",
    "validate_and_normalize_weights",
    "filter_criteria",
    "DeterministicEvaluator",
    "LLMEvaluator",
    "EvaluationEngine",
    "ReflectionEngine",
    "EvaluationRepository",
    "EvaluationService",
]
