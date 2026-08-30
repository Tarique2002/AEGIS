"""Strongly typed schemas for the AEGIS Evaluation & Reflection subsystem (Phase 4)."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import AegisBaseSchema, utc_now


class EvaluationType(str, Enum):
    """Core evaluation dimensions."""

    CORRECTNESS = "CORRECTNESS"
    COMPLETENESS = "COMPLETENESS"
    RELEVANCE = "RELEVANCE"
    SAFETY = "SAFETY"
    EFFICIENCY = "EFFICIENCY"
    TOOL_USAGE = "TOOL_USAGE"
    INSTRUCTION_FOLLOWING = "INSTRUCTION_FOLLOWING"


class FailureCategory(str, Enum):
    """Comprehensive failure taxonomy for agent executions."""

    NONE = "NONE"
    INCORRECT_RESULT = "INCORRECT_RESULT"
    INCOMPLETE_RESULT = "INCOMPLETE_RESULT"
    IRRELEVANT_RESPONSE = "IRRELEVANT_RESPONSE"
    TOOL_FAILURE = "TOOL_FAILURE"
    TOOL_MISUSE = "TOOL_MISUSE"
    TIMEOUT = "TIMEOUT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    LLM_ERROR = "LLM_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_INEFFICIENCY = "RESOURCE_INEFFICIENCY"
    INSTRUCTION_FOLLOWING_FAILURE = "INSTRUCTION_FOLLOWING_FAILURE"
    UNKNOWN = "UNKNOWN"


class RootCauseCategory(str, Enum):
    """Standardized root cause classifications for reflection."""

    INSUFFICIENT_CONTEXT = "insufficient_context"
    INCORRECT_TOOL_SELECTION = "incorrect_tool_selection"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    TOOL_FAILURE = "tool_failure"
    POOR_INSTRUCTION_FOLLOWING = "poor_instruction_following"
    INCOMPLETE_REASONING = "incomplete_reasoning"
    TIMEOUT = "timeout"
    POLICY_CONSTRAINT = "policy_constraint"
    EXTERNAL_DEPENDENCY = "external_dependency"
    UNKNOWN = "unknown"


class EvaluationCriterion(AegisBaseSchema):
    """Specification of an evaluation criterion and its configuration."""

    criterion_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    weight: float = Field(
        ..., ge=0.0, le=1.0, description="Relative importance weight between 0.0 and 1.0"
    )
    enabled: bool = Field(default=True)
    evaluation_type: EvaluationType


class CriterionScore(AegisBaseSchema):
    """Score, justification, and observable evidence for a single evaluated criterion."""

    criterion_id: str = Field(..., min_length=1)
    criterion_name: str = Field(..., min_length=1)
    score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized score strictly between 0.0 and 1.0"
    )
    weight: float = Field(..., ge=0.0, le=1.0)
    justification: str = Field(..., min_length=1)
    evidence: Any = Field(
        default=None, description="Observable execution facts, tool outputs, or metrics"
    )


class EvaluationRequest(AegisBaseSchema):
    """Client request to evaluate a completed agent run."""

    task_id: uuid.UUID
    run_id: uuid.UUID
    objective: str | None = None
    expected_result: str | None = None
    actual_result: str | None = None
    criteria: list[str] | None = Field(
        default=None, description="Optional subset of criterion_ids to evaluate"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(AegisBaseSchema):
    """
    Comprehensive evaluation record containing scores, pass/fail status,
    and diagnostic feedback.
    """

    evaluation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    run_id: uuid.UUID
    overall_score: float = Field(..., ge=0.0, le=1.0)
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    passed: bool = Field(...)
    failure_categories: list[FailureCategory] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evaluator: str = Field(default="composite")
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("failure_categories")
    @classmethod
    def validate_failure_categories(cls, v: list[FailureCategory]) -> list[FailureCategory]:
        if not v:
            return [FailureCategory.NONE]
        return v


class ReflectionRequest(AegisBaseSchema):
    """Request to generate and optionally persist reflection from an evaluation."""

    evaluation_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    persist_to_memory: bool = Field(
        default=False,
        description="Optionally store reflection record in AEGIS memory engine.",
    )


class ReflectionRecord(AegisBaseSchema):
    """
    Structured analytical reflection record capturing what went well,
    root causes, and recommendations.
    """

    reflection_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    run_id: uuid.UUID
    evaluation_id: uuid.UUID
    summary: str = Field(..., min_length=1)
    what_went_well: list[str] = Field(default_factory=list)
    what_went_wrong: list[str] = Field(default_factory=list)
    root_causes: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# LLM Structured Output Contracts
# ==============================================================================


class LLMCriterionEvaluation(AegisBaseSchema):
    """Schema for individual criterion scores returned by LLM Evaluator."""

    criterion_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    justification: str = Field(..., min_length=1)
    evidence: str | None = None


class LLMEvaluationOutput(AegisBaseSchema):
    """Strict schema for LLM-based semantic evaluation response."""

    evaluations: list[LLMCriterionEvaluation] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class LLMReflectionOutput(AegisBaseSchema):
    """Strict schema for LLM-based reflection synthesis."""

    summary: str = Field(..., min_length=1)
    what_went_well: list[str] = Field(default_factory=list)
    what_went_wrong: list[str] = Field(default_factory=list)
    root_causes: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
