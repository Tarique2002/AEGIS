"""Unit tests for Deterministic, LLM, and Composite Evaluation Engines."""

import uuid

import pytest
from app.evaluation.evaluator import DeterministicEvaluator, EvaluationEngine
from app.evaluation.policies import EvaluationPolicy
from app.evaluation.schemas import (
    EvaluationRequest,
    EvaluationResult,
    FailureCategory,
    LLMCriterionEvaluation,
    LLMEvaluationOutput,
)
from app.llm.base import LLMProvider, LLMResponse, ProviderMetadata, StructuredLLMResponse
from app.schemas.common import ChatMessage


class MockStructuredLLMProvider(LLMProvider):
    """Mock provider for testing LLMEvaluator."""

    def __init__(self, output: LLMEvaluationOutput | None = None, fail: bool = False) -> None:
        self.output = output
        self.fail = fail

    async def generate(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content="mock")

    async def generate_structured(self, messages: list[ChatMessage], response_model, **kwargs):
        if self.fail:
            raise RuntimeError("Provider connection error")
        return StructuredLLMResponse(
            data=self.output or LLMEvaluationOutput(),
            raw_text="{}",
        )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_name="mock", model_name="mock-eval")


@pytest.mark.asyncio
async def test_deterministic_successful_run() -> None:
    evaluator = DeterministicEvaluator()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    req = EvaluationRequest(
        task_id=task_id,
        run_id=run_id,
        expected_result="100",
        actual_result="100",
    )
    from app.evaluation.criteria import get_default_criteria

    criteria = get_default_criteria()

    exec_ctx = {
        "status": "completed",
        "result": "100",
        "events": [],
        "latency_ms": 250.0,
        "total_tokens": 150,
    }

    scores, failure_cats, strengths, weaknesses, recs = evaluator.evaluate_execution_facts(
        request=req,
        criteria=criteria,
        execution_context=exec_ctx,
    )

    assert FailureCategory.NONE in failure_cats
    corr_score = next(s for s in scores if s.criterion_id == "correctness")
    assert corr_score.score == 1.0
    safe_score = next(s for s in scores if s.criterion_id == "safety")
    assert safe_score.score == 1.0


@pytest.mark.asyncio
async def test_deterministic_tool_failure_and_timeout() -> None:
    evaluator = DeterministicEvaluator()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    req = EvaluationRequest(task_id=task_id, run_id=run_id)
    from app.evaluation.criteria import get_default_criteria

    criteria = get_default_criteria()

    exec_ctx = {
        "status": "timed_out",
        "error": "Operation exceeded 30s timeout limit",
        "result": None,
        "events": [
            {
                "event_type": "TOOL_CALL_FAILED",
                "sequence_number": 1,
                "payload": {"error": "Tool crash"},
            },
            {"event_type": "TOOL_CALL_TIMEOUT", "sequence_number": 2, "payload": {}},
        ],
    }

    scores, failure_cats, strengths, weaknesses, recs = evaluator.evaluate_execution_facts(
        request=req,
        criteria=criteria,
        execution_context=exec_ctx,
    )

    assert FailureCategory.TIMEOUT in failure_cats
    assert FailureCategory.TOOL_FAILURE in failure_cats
    assert FailureCategory.INCOMPLETE_RESULT in failure_cats


@pytest.mark.asyncio
async def test_deterministic_policy_violation() -> None:
    evaluator = DeterministicEvaluator()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()

    req = EvaluationRequest(task_id=task_id, run_id=run_id)
    from app.evaluation.criteria import get_default_criteria

    criteria = get_default_criteria()

    exec_ctx = {
        "status": "failed",
        "events": [
            {
                "event_type": "TOOL_CALL_REJECTED",
                "sequence_number": 1,
                "payload": {"reason": "Policy violation"},
            },
        ],
    }

    scores, failure_cats, strengths, weaknesses, recs = evaluator.evaluate_execution_facts(
        request=req,
        criteria=criteria,
        execution_context=exec_ctx,
    )

    assert FailureCategory.POLICY_VIOLATION in failure_cats
    safety_score = next(s for s in scores if s.criterion_id == "safety")
    assert safety_score.score == 0.0


@pytest.mark.asyncio
async def test_composite_evaluation_engine_with_llm() -> None:
    mock_output = LLMEvaluationOutput(
        evaluations=[
            LLMCriterionEvaluation(
                criterion_id="correctness",
                score=0.95,
                justification="Highly accurate calculation and explanation.",
            ),
            LLMCriterionEvaluation(
                criterion_id="completeness",
                score=0.90,
                justification="Covered all aspects requested.",
            ),
        ],
        strengths=["Clear concise step by step output"],
        weaknesses=[],
        recommendations=["Keep using current reasoning strategy"],
    )
    provider = MockStructuredLLMProvider(output=mock_output)
    engine = EvaluationEngine(llm_provider=provider, policy=EvaluationPolicy(pass_threshold=0.70))

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    req = EvaluationRequest(task_id=task_id, run_id=run_id, actual_result="Calculation result: 100")

    result: EvaluationResult = await engine.evaluate(
        request=req,
        execution_context={"status": "completed", "result": "100"},
    )

    assert result.passed is True
    assert result.overall_score >= 0.70
    assert result.evaluator == "composite"
    assert "Clear concise step by step output" in result.strengths


@pytest.mark.asyncio
async def test_composite_evaluation_engine_llm_failure_fallback() -> None:
    failing_provider = MockStructuredLLMProvider(fail=True)
    engine = EvaluationEngine(llm_provider=failing_provider)

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    req = EvaluationRequest(
        task_id=task_id, run_id=run_id, actual_result="100", expected_result="100"
    )

    result: EvaluationResult = await engine.evaluate(
        request=req,
        execution_context={"status": "completed", "result": "100"},
    )

    # Should gracefully degrade to deterministic evaluation
    assert result.passed is True
    assert result.overall_score >= 0.90
    assert result.evaluator == "deterministic"
