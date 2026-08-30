"""Unit tests for ReflectionEngine, root-cause taxonomy, and structured feedback."""

import uuid

import pytest
from app.evaluation.reflection import ReflectionEngine
from app.evaluation.schemas import (
    CriterionScore,
    EvaluationResult,
    FailureCategory,
    LLMReflectionOutput,
    ReflectionRecord,
    ReflectionRequest,
    RootCauseCategory,
)
from app.llm.base import LLMProvider, LLMResponse, ProviderMetadata, StructuredLLMResponse
from app.schemas.common import ChatMessage


class MockReflectionLLMProvider(LLMProvider):
    """Mock provider for testing LLM-assisted reflection."""

    def __init__(self, output: LLMReflectionOutput | None = None) -> None:
        self.output = output

    async def generate(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content="mock")

    async def generate_structured(self, messages: list[ChatMessage], response_model, **kwargs):
        return StructuredLLMResponse(
            data=self.output
            or LLMReflectionOutput(
                summary="Synthesized reflection summary.",
                what_went_well=["Safe execution"],
                what_went_wrong=["Tool syntax error"],
                root_causes=["invalid_tool_arguments"],
                improvement_suggestions=["Validate syntax before call"],
                confidence=0.9,
            ),
            raw_text="{}",
        )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_name="mock", model_name="mock-reflector")


@pytest.mark.asyncio
async def test_deterministic_reflection_successful_run() -> None:
    engine = ReflectionEngine()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    eval_result = EvaluationResult(
        evaluation_id=eval_id,
        task_id=task_id,
        run_id=run_id,
        overall_score=0.95,
        criterion_scores=[
            CriterionScore(
                criterion_id="correctness",
                criterion_name="Correctness",
                score=1.0,
                weight=1.0,
                justification="Accurate",
            )
        ],
        passed=True,
        failure_categories=[FailureCategory.NONE],
        strengths=["Quick completion", "Zero errors"],
        weaknesses=[],
        recommendations=["Keep parameters"],
    )

    req = ReflectionRequest(evaluation_id=eval_id)
    reflection: ReflectionRecord = await engine.reflect(
        evaluation=eval_result,
        request=req,
        execution_context={"status": "completed"},
    )

    assert reflection.evaluation_id == eval_id
    assert reflection.confidence == 1.0
    assert "Quick completion" in reflection.what_went_well
    assert len(reflection.root_causes) == 0


@pytest.mark.asyncio
async def test_deterministic_reflection_failed_run_root_causes() -> None:
    engine = ReflectionEngine()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    eval_result = EvaluationResult(
        evaluation_id=eval_id,
        task_id=task_id,
        run_id=run_id,
        overall_score=0.40,
        criterion_scores=[],
        passed=False,
        failure_categories=[
            FailureCategory.TOOL_FAILURE,
            FailureCategory.POLICY_VIOLATION,
        ],
        strengths=[],
        weaknesses=["Tool threw exception", "Unauthorized access blocked"],
        recommendations=["Review access controls"],
    )

    req = ReflectionRequest(evaluation_id=eval_id)
    reflection: ReflectionRecord = await engine.reflect(
        evaluation=eval_result,
        request=req,
        execution_context={"status": "failed"},
    )

    assert reflection.confidence <= 0.85
    assert RootCauseCategory.TOOL_FAILURE.value in reflection.root_causes
    assert RootCauseCategory.POLICY_CONSTRAINT.value in reflection.root_causes


@pytest.mark.asyncio
async def test_llm_assisted_reflection() -> None:
    mock_llm_output = LLMReflectionOutput(
        summary="Detailed semantic diagnosis of failure.",
        what_went_well=["Detected failure gracefully"],
        what_went_wrong=["Passed invalid JSON to calculator"],
        root_causes=["invalid_tool_arguments"],
        improvement_suggestions=["Sanitize arithmetic expression string"],
        confidence=0.92,
    )
    provider = MockReflectionLLMProvider(output=mock_llm_output)
    engine = ReflectionEngine(llm_provider=provider)

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    eval_result = EvaluationResult(
        evaluation_id=eval_id,
        task_id=task_id,
        run_id=run_id,
        overall_score=0.5,
        criterion_scores=[],
        passed=False,
        failure_categories=[FailureCategory.TOOL_MISUSE],
    )

    req = ReflectionRequest(evaluation_id=eval_id)
    reflection: ReflectionRecord = await engine.reflect(
        evaluation=eval_result,
        request=req,
    )

    assert reflection.summary == "Detailed semantic diagnosis of failure."
    assert "Sanitize arithmetic expression string" in reflection.improvement_suggestions
    assert reflection.confidence == 0.92
