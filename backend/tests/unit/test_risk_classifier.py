"""Unit tests for RiskAssessmentEngine and classification matrix."""

import uuid

from app.safety.risk import RiskAssessmentEngine
from app.safety.schemas import RiskCategory, RiskLevel, SafetyContext


def test_risk_classifier_computation() -> None:
    engine = RiskAssessmentEngine()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="calculate addition",
        tool_name="calculator",
        arguments_metadata={"expression": "2 + 2"},
    )
    assessment = engine.assess(ctx)
    assert assessment.level == RiskLevel.LOW
    assert RiskCategory.COMPUTATION in assessment.categories


def test_risk_classifier_memory_write() -> None:
    engine = RiskAssessmentEngine()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="write_memory",
        arguments_metadata={"content": "new memory"},
    )
    assessment = engine.assess(ctx)
    assert assessment.level == RiskLevel.MEDIUM
    assert RiskCategory.MEMORY_WRITE in assessment.categories


def test_risk_classifier_destructive_critical() -> None:
    engine = RiskAssessmentEngine()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="delete and drop all database tables",
    )
    assessment = engine.assess(ctx)
    assert assessment.level == RiskLevel.CRITICAL
    assert RiskCategory.DESTRUCTIVE in assessment.categories


def test_risk_classifier_code_execution_critical() -> None:
    engine = RiskAssessmentEngine()
    ctx = SafetyContext(
        user_id=uuid.uuid4(),
        action="execute python script code eval()",
    )
    assessment = engine.assess(ctx)
    assert assessment.level == RiskLevel.CRITICAL
    assert RiskCategory.CODE_EXECUTION in assessment.categories
