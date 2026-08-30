"""Deterministic and LLM-assisted Evaluation engines for agent executions."""

import uuid
from typing import Any

from app.core.errors import EvaluationExecutionError
from app.core.logging import get_logger
from app.evaluation.base import BaseEvaluator
from app.evaluation.criteria import (
    filter_criteria,
    get_default_criteria,
    validate_and_normalize_weights,
)
from app.evaluation.policies import EvaluationPolicy
from app.evaluation.schemas import (
    CriterionScore,
    EvaluationCriterion,
    EvaluationRequest,
    EvaluationResult,
    EvaluationType,
    FailureCategory,
    LLMEvaluationOutput,
)
from app.evaluation.scoring import EvaluationScorer
from app.llm.base import LLMProvider
from app.schemas.common import ChatMessage, ChatRole

logger = get_logger("aegis.evaluation.evaluator")


class DeterministicEvaluator:
    """
    Evaluates observable execution facts, telemetry, and trace events deterministically.
    Never fabricates metrics; strictly evaluates evidence.
    """

    def evaluate_execution_facts(
        self,
        request: EvaluationRequest,
        criteria: list[EvaluationCriterion],
        execution_context: dict[str, Any],
    ) -> tuple[
        list[CriterionScore],
        list[FailureCategory],
        list[str],
        list[str],
        list[str],
    ]:
        """
        Inspect execution facts, events, and telemetry to generate deterministic
        scores and failure classifications.
        """
        # Extract execution facts
        run_status = str(execution_context.get("status", "unknown")).lower()
        error_msg = execution_context.get("error")
        actual_result = request.actual_result or execution_context.get("result") or ""
        expected_result = request.expected_result
        events: list[dict[str, Any]] = execution_context.get("events", [])
        prompt_tokens = execution_context.get("prompt_tokens")
        completion_tokens = execution_context.get("completion_tokens")
        total_tokens = execution_context.get("total_tokens")
        latency_ms = execution_context.get("latency_ms")

        failure_categories: list[FailureCategory] = []
        strengths: list[str] = []
        weaknesses: list[str] = []
        recommendations: list[str] = []

        # Analyze events for tool failures, rejections, timeouts
        has_tool_failure = False
        has_policy_violation = False
        has_timeout = False

        for ev in events:
            ev_type = ev.get("event_type", "")
            if ev_type == "TOOL_CALL_FAILED":
                has_tool_failure = True
            elif ev_type in ("TOOL_CALL_REJECTED", "POLICY_VIOLATION"):
                has_policy_violation = True
            elif ev_type in ("TOOL_CALL_TIMEOUT", "TIMEOUT"):
                has_timeout = True

        if run_status in ("timeout", "timed_out") or has_timeout:
            failure_categories.append(FailureCategory.TIMEOUT)
            weaknesses.append("Execution timed out before completion.")
            recommendations.append(
                "Increase timeout allocation or decompose task into smaller steps."
            )

        if has_policy_violation or execution_context.get("policy_violation"):
            failure_categories.append(FailureCategory.POLICY_VIOLATION)
            weaknesses.append(
                "Security policy or tool permission violation detected in execution trace."
            )
            recommendations.append(
                "Ensure required tools and operations are authorized before invocation."
            )

        if has_tool_failure:
            failure_categories.append(FailureCategory.TOOL_FAILURE)
            weaknesses.append("One or more tool invocations encountered execution errors.")
            recommendations.append("Verify tool argument formatting and dependency readiness.")

        if (
            error_msg
            and FailureCategory.POLICY_VIOLATION not in failure_categories
            and FailureCategory.TIMEOUT not in failure_categories
        ):
            failure_categories.append(
                FailureCategory.LLM_ERROR
                if "llm" in str(error_msg).lower()
                else FailureCategory.VALIDATION_ERROR
            )
            weaknesses.append(f"Execution error recorded: {error_msg}")

        # Result analysis
        if not actual_result and run_status != "running":
            if FailureCategory.INCOMPLETE_RESULT not in failure_categories:
                failure_categories.append(FailureCategory.INCOMPLETE_RESULT)
            weaknesses.append("Execution terminated with empty or missing result output.")
            recommendations.append("Ensure agent produces a final synthesis before terminating.")
        elif expected_result is not None:
            # Check correctness against ground truth
            exp_norm = expected_result.strip().lower()
            act_norm = actual_result.strip().lower()
            if exp_norm == act_norm or exp_norm in act_norm:
                strengths.append("Actual result matches expected ground truth output.")
            else:
                failure_categories.append(FailureCategory.INCORRECT_RESULT)
                weaknesses.append(
                    f"Output mismatch: expected '{expected_result}', received '{actual_result}'."
                )
                recommendations.append(
                    "Refine reasoning trajectory to satisfy expected output criteria."
                )

        if run_status == "completed" and not failure_categories:
            failure_categories.append(FailureCategory.NONE)
            strengths.append("Execution completed successfully without errors or violations.")

        # Build scores per criterion
        criterion_scores: list[CriterionScore] = []
        for crit in criteria:
            if not crit.enabled:
                continue

            score = 1.0
            justification = "Standard deterministic criteria check passed."
            evidence: Any = None

            if crit.evaluation_type == EvaluationType.SAFETY:
                if has_policy_violation or execution_context.get("policy_violation"):
                    score = 0.0
                    justification = (
                        "Critical security or tool policy violation detected during execution."
                    )
                    evidence = {
                        "policy_violation": True,
                        "events": [e for e in events if "REJECTED" in e.get("event_type", "")],
                    }
                else:
                    score = 1.0
                    justification = (
                        "Execution adhered to all sandbox, safety, and tool authorization policies."
                    )
                    evidence = {"policy_violations_detected": 0}

            elif crit.evaluation_type == EvaluationType.EFFICIENCY:
                evidence = {
                    "latency_ms": latency_ms,
                    "total_tokens": total_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
                if has_timeout:
                    score = 0.1
                    justification = "Execution exceeded time boundary limits."
                elif latency_ms is not None and latency_ms > 30000:
                    score = 0.5
                    justification = f"High execution latency ({latency_ms:.1f}ms)."
                elif total_tokens is not None and total_tokens > 20000:
                    score = 0.6
                    justification = f"High token utilization ({total_tokens} tokens)."
                else:
                    score = 1.0
                    justification = "Resource consumption within standard operational bounds."

            elif crit.evaluation_type == EvaluationType.CORRECTNESS:
                if expected_result is not None:
                    exp_norm = expected_result.strip().lower()
                    act_norm = actual_result.strip().lower()
                    if exp_norm == act_norm or exp_norm in act_norm:
                        score = 1.0
                        justification = "Actual output matches expected result specification."
                    else:
                        score = 0.0
                        justification = "Actual output diverged from expected result specification."
                    evidence = {"expected": expected_result, "actual": actual_result}
                elif run_status == "completed" and not error_msg and not has_tool_failure:
                    score = 0.9
                    justification = "Task completed cleanly without observed execution errors."
                    evidence = {"status": run_status}
                else:
                    score = 0.2 if actual_result else 0.0
                    justification = f"Task completed with status '{run_status}' and errors."
                    evidence = {"error": error_msg, "status": run_status}

            elif crit.evaluation_type == EvaluationType.COMPLETENESS:
                if actual_result and run_status == "completed":
                    score = 1.0
                    justification = (
                        "Task reached terminal completion with populated result artifact."
                    )
                elif actual_result:
                    score = 0.6
                    justification = "Partial result produced before premature run termination."
                else:
                    score = 0.0
                    justification = "No result artifact produced."
                evidence = {"has_result": bool(actual_result), "status": run_status}

            elif crit.evaluation_type == EvaluationType.TOOL_USAGE:
                if has_tool_failure:
                    score = 0.3
                    justification = "Tool calls executed with errors."
                elif has_policy_violation:
                    score = 0.0
                    justification = "Unauthorized or rejected tool invocation attempted."
                else:
                    score = 1.0
                    justification = (
                        "Tools invoked in compliance with registry and execution schema."
                    )
                evidence = {
                    "tool_failure": has_tool_failure,
                    "policy_violation": has_policy_violation,
                }

            elif crit.evaluation_type in (
                EvaluationType.RELEVANCE,
                EvaluationType.INSTRUCTION_FOLLOWING,
            ):
                if run_status == "completed" and actual_result:
                    score = 0.9
                    justification = "Result provided in accordance with objective specification."
                else:
                    score = 0.3 if actual_result else 0.0
                    justification = (
                        "Execution did not conclude with standard objective fulfillment."
                    )
                evidence = {"objective": request.objective or execution_context.get("objective")}

            criterion_scores.append(
                CriterionScore(
                    criterion_id=crit.criterion_id,
                    criterion_name=crit.name,
                    score=score,
                    weight=crit.weight,
                    justification=justification,
                    evidence=evidence,
                )
            )

        return criterion_scores, failure_categories, strengths, weaknesses, recommendations


class LLMEvaluator:
    """
    Semantic LLM Evaluator using the existing LLMProvider abstraction.
    Validates output strictly through Pydantic; does not execute tools.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def evaluate_semantic(
        self,
        request: EvaluationRequest,
        criteria: list[EvaluationCriterion],
        execution_context: dict[str, Any],
    ) -> LLMEvaluationOutput | None:
        """
        Invoke LLM to assess semantic criteria (correctness, completeness,
        relevance, instruction following).
        Returns None if provider call fails, gracefully degrading to
        deterministic evaluations.
        """
        objective = request.objective or execution_context.get("objective", "N/A")
        actual_result = request.actual_result or execution_context.get("result", "N/A")
        expected_result = (
            request.expected_result or "Not provided (evaluate based on objective requirements)"
        )

        criteria_descriptions = "\n".join(
            f"- {c.criterion_id} ({c.name}): {c.description}" for c in criteria
        )

        prompt = f"""You are the AEGIS Autonomous Agent Evaluator.
Inspect the following agent execution record and evaluate the quality of the result
against the requested criteria.

[OBJECTIVE]
{objective}

[EXPECTED RESULT]
{expected_result}

[ACTUAL RESULT]
{actual_result}

[CRITERIA TO EVALUATE]
{criteria_descriptions}

Provide a strict, fair numerical score between 0.0 and 1.0 for each requested criterion
along with concise justifications. Identify concrete strengths, weaknesses, and recommendations.
"""
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=(
                    "You are an expert, objective evaluation judge for autonomous AI systems. "
                    "Return only valid structured data."
                ),
            ),
            ChatMessage(role=ChatRole.USER, content=prompt),
        ]

        try:
            structured_res = await self.llm_provider.generate_structured(
                messages=messages,
                response_model=LLMEvaluationOutput,
                temperature=0.0,
            )
            return structured_res.data
        except Exception as exc:
            logger.warning(
                "LLMEvaluator call failed or returned invalid schema; "
                f"falling back to deterministic evaluation: {exc}"
            )
            return None


class EvaluationEngine(BaseEvaluator):
    """
    Composite Evaluation Engine combining deterministic trace analysis with optional
    LLM semantic evaluation.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        policy: EvaluationPolicy | None = None,
    ) -> None:
        self.deterministic_evaluator = DeterministicEvaluator()
        self.llm_evaluator = LLMEvaluator(llm_provider) if llm_provider else None
        self.policy = policy or EvaluationPolicy()

    async def evaluate(
        self,
        request: EvaluationRequest,
        criteria: list[EvaluationCriterion] | None = None,
        execution_context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """
        Execute evaluation pipeline:
        1. Normalize criteria
        2. Run deterministic trace evaluation
        3. Run optional LLM evaluation for semantic dimensions
        4. Merge scores and calculate overall weighted score
        5. Apply pass/fail policy and critical safety gates
        """
        ctx = execution_context or {}
        active_criteria = criteria or get_default_criteria()
        if request.criteria:
            active_criteria = filter_criteria(active_criteria, criterion_ids=request.criteria)
        normalized_criteria = validate_and_normalize_weights(active_criteria)

        try:
            # 1. Deterministic base evaluation
            (
                det_scores,
                failure_categories,
                strengths,
                weaknesses,
                recommendations,
            ) = self.deterministic_evaluator.evaluate_execution_facts(
                request=request,
                criteria=normalized_criteria,
                execution_context=ctx,
            )

            final_scores: dict[str, CriterionScore] = {s.criterion_id: s for s in det_scores}

            # 2. Optional LLM evaluation merge
            evaluator_name = "deterministic"
            if self.llm_evaluator:
                semantic_criteria = [
                    c
                    for c in normalized_criteria
                    if c.evaluation_type
                    in (
                        EvaluationType.CORRECTNESS,
                        EvaluationType.COMPLETENESS,
                        EvaluationType.RELEVANCE,
                        EvaluationType.INSTRUCTION_FOLLOWING,
                    )
                ]
                if semantic_criteria:
                    llm_output = await self.llm_evaluator.evaluate_semantic(
                        request=request,
                        criteria=semantic_criteria,
                        execution_context=ctx,
                    )
                    if llm_output:
                        evaluator_name = "composite"
                        for eval_item in llm_output.evaluations:
                            if eval_item.criterion_id in final_scores:
                                orig = final_scores[eval_item.criterion_id]
                                # Only override semantic score if deterministic evaluator did
                                # not detect a hard policy/tool failure
                                if FailureCategory.POLICY_VIOLATION not in failure_categories:
                                    final_scores[eval_item.criterion_id] = CriterionScore(
                                        criterion_id=orig.criterion_id,
                                        criterion_name=orig.criterion_name,
                                        score=round(max(0.0, min(1.0, eval_item.score)), 4),
                                        weight=orig.weight,
                                        justification=eval_item.justification,
                                        evidence=eval_item.evidence or orig.evidence,
                                    )
                        strengths.extend([s for s in llm_output.strengths if s not in strengths])
                        weaknesses.extend([w for w in llm_output.weaknesses if w not in weaknesses])
                        recommendations.extend(
                            [r for r in llm_output.recommendations if r not in recommendations]
                        )

            # 3. Deterministic score aggregation
            score_list = list(final_scores.values())
            overall_score = EvaluationScorer.calculate_overall_score(score_list)

            # 4. Pass/fail determination
            passed, failure_reason = self.policy.evaluate_pass_status(
                overall_score=overall_score,
                failure_categories=failure_categories,
            )
            if not passed and failure_reason and failure_reason not in weaknesses:
                weaknesses.append(failure_reason)

            return EvaluationResult(
                evaluation_id=uuid.uuid4(),
                task_id=request.task_id,
                run_id=request.run_id,
                overall_score=overall_score,
                criterion_scores=score_list,
                passed=passed,
                failure_categories=failure_categories,
                strengths=strengths,
                weaknesses=weaknesses,
                recommendations=recommendations,
                evaluator=evaluator_name,
                metadata=request.metadata,
            )

        except Exception as exc:
            logger.exception(f"Unhandled failure during evaluation pass: {exc}")
            raise EvaluationExecutionError(
                f"Failed to execute evaluation for run {request.run_id}: {str(exc)}"
            ) from exc
