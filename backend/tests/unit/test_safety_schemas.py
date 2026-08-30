"""Unit tests for Phase 8 Safety schemas and models."""

import uuid

from app.safety.schemas import (
    RateLimitResult,
    RiskAssessment,
    RiskCategory,
    RiskLevel,
    SafetyBudget,
    SafetyContext,
    SafetyDecision,
    SafetyDecisionType,
)


def test_safety_schemas_instantiation() -> None:
    user_id = uuid.uuid4()
    context = SafetyContext(
        user_id=user_id,
        action="test_action",
        requested_capabilities=["read_only"],
        risk_level=RiskLevel.LOW,
        risk_categories=[RiskCategory.READ_ONLY],
    )
    assert context.user_id == user_id
    assert context.action == "test_action"

    assessment = RiskAssessment(
        level=RiskLevel.LOW,
        categories=[RiskCategory.COMPUTATION],
        factors=["Deterministic calculation"],
        explanation="Safe math",
    )
    assert assessment.level == RiskLevel.LOW
    assert assessment.confidence == 1.0

    decision = SafetyDecision(
        allowed=True,
        decision_type=SafetyDecisionType.ALLOW,
        risk_level=RiskLevel.LOW,
        reason="Approved",
    )
    assert decision.allowed is True
    assert decision.decision_type == SafetyDecisionType.ALLOW


def test_safety_budget_and_rate_limit_schemas() -> None:
    budget = SafetyBudget(requests=5, tool_calls=2)
    assert budget.requests == 5
    assert budget.tool_calls == 2

    rate_res = RateLimitResult(
        allowed=True,
        limit=120,
        remaining=119,
        reset_seconds=60,
        retry_after_seconds=0,
    )
    assert rate_res.allowed is True
    assert rate_res.remaining == 119
