"""Abstract base classes for Evaluation and Reflection engines."""

from abc import ABC, abstractmethod
from typing import Any

from app.evaluation.schemas import (
    EvaluationCriterion,
    EvaluationRequest,
    EvaluationResult,
    ReflectionRecord,
    ReflectionRequest,
)


class BaseEvaluator(ABC):
    """Abstract interface for evaluating agent execution runs."""

    @abstractmethod
    async def evaluate(
        self,
        request: EvaluationRequest,
        criteria: list[EvaluationCriterion],
        execution_context: dict[str, Any],
    ) -> EvaluationResult:
        """Evaluate an execution run against specified criteria using execution context facts."""
        ...


class BaseReflectionEngine(ABC):
    """
    Abstract interface for extracting structured reflection records from
    evaluation results.
    """

    @abstractmethod
    async def reflect(
        self,
        evaluation: EvaluationResult,
        request: ReflectionRequest,
        execution_context: dict[str, Any] | None = None,
    ) -> ReflectionRecord:
        """
        Synthesize structured reflections, root causes, and recommendations
        from an evaluation.
        """
        ...
