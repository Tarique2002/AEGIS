"""Reflection Engine synthesizing structured improvement observations and root causes."""

import uuid
from typing import Any

from app.core.logging import get_logger
from app.evaluation.base import BaseReflectionEngine
from app.evaluation.schemas import (
    EvaluationResult,
    FailureCategory,
    LLMReflectionOutput,
    ReflectionRecord,
    ReflectionRequest,
    RootCauseCategory,
)
from app.llm.base import LLMProvider
from app.schemas.common import ChatMessage, ChatRole

logger = get_logger("aegis.evaluation.reflection")


class ReflectionEngine(BaseReflectionEngine):
    """
    Synthesizes structured reflection records from evaluation results.
    Identifies what went well, what went wrong, evidence-backed root causes, and recommendations.
    Guarantees: No automatic mutation of agent runtime, prompts, or policies.
    """

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def _map_deterministic_root_causes(
        self,
        evaluation: EvaluationResult,
        execution_context: dict[str, Any],
    ) -> list[str]:
        """Classify root causes strictly based on observable failure categories and evidence."""
        root_causes: list[str] = []
        failure_cats = set(evaluation.failure_categories)

        if FailureCategory.TIMEOUT in failure_cats:
            root_causes.append(RootCauseCategory.TIMEOUT.value)

        if FailureCategory.TOOL_FAILURE in failure_cats:
            root_causes.append(RootCauseCategory.TOOL_FAILURE.value)

        if FailureCategory.TOOL_MISUSE in failure_cats:
            root_causes.append(RootCauseCategory.INVALID_TOOL_ARGUMENTS.value)

        if FailureCategory.POLICY_VIOLATION in failure_cats:
            root_causes.append(RootCauseCategory.POLICY_CONSTRAINT.value)

        if FailureCategory.INSTRUCTION_FOLLOWING_FAILURE in failure_cats:
            root_causes.append(RootCauseCategory.POOR_INSTRUCTION_FOLLOWING.value)

        if (
            FailureCategory.INCORRECT_RESULT in failure_cats
            or FailureCategory.INCOMPLETE_RESULT in failure_cats
        ):
            root_causes.append(RootCauseCategory.INCOMPLETE_REASONING.value)

        if not root_causes and FailureCategory.NONE not in failure_cats:
            root_causes.append(RootCauseCategory.UNKNOWN.value)

        return root_causes

    async def reflect(
        self,
        evaluation: EvaluationResult,
        request: ReflectionRequest,
        execution_context: dict[str, Any] | None = None,
    ) -> ReflectionRecord:
        """
        Synthesize reflection record from evaluation result.
        Uses deterministic facts first and optionally enriches via LLMProvider when available.
        """
        ctx = execution_context or {}
        deterministic_root_causes = self._map_deterministic_root_causes(evaluation, ctx)

        what_went_well = list(evaluation.strengths)
        what_went_wrong = list(evaluation.weaknesses)
        improvement_suggestions = list(evaluation.recommendations)
        status_label = "PASSED" if evaluation.passed else "FAILED"
        summary = (
            f"Execution evaluation score {evaluation.overall_score:.2f} ({status_label}). "
            f"Identified {len(evaluation.failure_categories)} failure category entries."
        )
        confidence = 1.0 if evaluation.passed else 0.85

        # If LLMProvider is present and execution failed or has weaknesses,
        # perform semantic reflection
        if self.llm_provider and (not evaluation.passed or evaluation.weaknesses):
            strengths_str = (
                "\n".join(f"- {s}" for s in evaluation.strengths)
                if evaluation.strengths
                else "None recorded"
            )
            weaknesses_str = (
                "\n".join(f"- {w}" for w in evaluation.weaknesses)
                if evaluation.weaknesses
                else "None recorded"
            )
            root_causes_str = (
                ", ".join(deterministic_root_causes) if deterministic_root_causes else "None"
            )
            prompt = f"""You are the AEGIS Autonomous Agent Reflection Engine.
Analyze this agent execution evaluation and formulate structured, objective reflection points.
Distinguish clearly between observed facts, inferences, and actionable improvement recommendations.

[EVALUATION SCORE]
Overall Score: {evaluation.overall_score:.2f} (Passed: {evaluation.passed})

[FAILURE CATEGORIES]
{', '.join(f.value for f in evaluation.failure_categories)}

[STRENGTHS]
{strengths_str}

[WEAKNESSES]
{weaknesses_str}

[EXISTING ROOT CAUSES]
{root_causes_str}

Synthesize:
1. Concise executive summary
2. What went well (observed successes)
3. What went wrong (observed failures)
4. Concrete root causes (do not invent unevidenced causes)
5. Actionable improvement suggestions
6. Analytical confidence score (0.0 to 1.0)
"""
            try:
                messages = [
                    ChatMessage(
                        role=ChatRole.SYSTEM,
                        content=(
                            "You are an expert diagnostic reflection analyst for "
                            "autonomous AI agents. Return only structured data."
                        ),
                    ),
                    ChatMessage(role=ChatRole.USER, content=prompt),
                ]
                llm_res = await self.llm_provider.generate_structured(
                    messages=messages,
                    response_model=LLMReflectionOutput,
                    temperature=0.0,
                )
                ref_data = llm_res.data
                summary = ref_data.summary
                what_went_well = ref_data.what_went_well or what_went_well
                what_went_wrong = ref_data.what_went_wrong or what_went_wrong
                # Combine root causes ensuring standard taxonomy
                for rc in ref_data.root_causes:
                    if rc not in deterministic_root_causes:
                        deterministic_root_causes.append(rc)
                improvement_suggestions = (
                    ref_data.improvement_suggestions or improvement_suggestions
                )
                confidence = max(0.0, min(1.0, ref_data.confidence))
            except Exception as exc:
                logger.warning(
                    "LLM reflection synthesis failed; "
                    f"using deterministic reflection baseline: {exc}"
                )

        if not what_went_well and evaluation.passed:
            what_went_well.append("Execution met all quality thresholds and completed cleanly.")

        if not what_went_wrong and not evaluation.passed:
            what_went_wrong.append(f"Run failed pass threshold ({evaluation.overall_score:.2f}).")

        if not improvement_suggestions:
            if evaluation.passed:
                improvement_suggestions.append(
                    "Maintain existing planning and execution parameters."
                )
            else:
                improvement_suggestions.append("Review failed tool calls or constraint violations.")

        return ReflectionRecord(
            reflection_id=uuid.uuid4(),
            task_id=evaluation.task_id,
            run_id=evaluation.run_id,
            evaluation_id=evaluation.evaluation_id,
            summary=summary,
            what_went_well=what_went_well,
            what_went_wrong=what_went_wrong,
            root_causes=deterministic_root_causes,
            improvement_suggestions=improvement_suggestions,
            confidence=round(confidence, 4),
            metadata=request.metadata,
        )
