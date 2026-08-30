"""Unit tests for ProgressTracker, repetition guards, and AgentGuardrails."""

import pytest
from app.agent_loop.guardrails import AgentGuardrails, ProgressTracker
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentDecision, DecisionType
from app.core.errors import InvalidDecisionError, SafetyStopTriggeredError


def test_progress_tracker_score_stagnation() -> None:
    tracker = ProgressTracker(policy=AgentLoopPolicy(max_stagnant_iterations=2))

    tracker.record_iteration(eval_score=0.7)
    is_stagnant, _ = tracker.check_stagnation()
    assert is_stagnant is False

    # Score drops or remains unchanged -> stagnant count 1
    tracker.record_iteration(eval_score=0.65)
    is_stagnant, _ = tracker.check_stagnation()
    assert is_stagnant is False

    # Stagnant count 2 -> triggers stagnation
    tracker.record_iteration(eval_score=0.60)
    is_stagnant, reason = tracker.check_stagnation()
    assert is_stagnant is True
    assert "No progress detected" in reason


def test_progress_tracker_repeated_failure_detection() -> None:
    tracker = ProgressTracker()
    failure = {"tool_name": "calculator", "node_type": "TOOL", "error": "Invalid syntax"}

    tracker.record_iteration(failures=[failure])
    tracker.record_iteration(failures=[failure])
    tracker.record_iteration(failures=[failure])

    is_stagnant, reason = tracker.check_stagnation()
    assert is_stagnant is True
    assert "Repeated identical failure detected" in reason


def test_agent_guardrails_validation_success() -> None:
    guardrails = AgentGuardrails()
    tracker = ProgressTracker()
    decision = AgentDecision(
        iteration_number=1,
        decision_type=DecisionType.CONTINUE,
        rationale="Executing next plan node.",
    )
    # Should not raise
    guardrails.validate_decision(decision, tracker)


def test_agent_guardrails_empty_rationale_rejected() -> None:
    guardrails = AgentGuardrails()
    tracker = ProgressTracker()
    decision = AgentDecision(
        iteration_number=1,
        decision_type=DecisionType.CONTINUE,
        rationale="   ",
    )
    with pytest.raises(InvalidDecisionError, match="rationale cannot be empty"):
        guardrails.validate_decision(decision, tracker)


def test_agent_guardrails_safety_stop_triggers_error() -> None:
    guardrails = AgentGuardrails()
    tracker = ProgressTracker()
    decision = AgentDecision(
        iteration_number=1,
        decision_type=DecisionType.SAFETY_STOP,
        rationale="Harmful instruction detected in memory context.",
    )
    with pytest.raises(SafetyStopTriggeredError, match="Safety guardrail triggered stop"):
        guardrails.validate_decision(decision, tracker)
