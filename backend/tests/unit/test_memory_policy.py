"""Unit tests for MemoryPolicy validation, ownership enforcement, and ranking calculation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.memory.errors import (
    MemoryOwnershipError,
    MemoryPolicyViolationError,
    MemoryValidationError,
)
from app.memory.policies import MemoryPolicy
from app.memory.schemas import MemoryCandidate


def test_memory_policy_candidate_validation_success():
    policy = MemoryPolicy(max_content_length=1000)
    candidate = MemoryCandidate(content="Valid memory text", importance=0.8)
    policy.validate_candidate(candidate)  # Should not raise


def test_memory_policy_empty_content():
    policy = MemoryPolicy()
    candidate = MemoryCandidate.model_construct(content="   ")
    with pytest.raises(MemoryValidationError):
        policy.validate_candidate(candidate)


def test_memory_policy_content_size_limit():
    policy = MemoryPolicy(max_content_length=50)
    candidate = MemoryCandidate(content="A" * 51)
    with pytest.raises(MemoryPolicyViolationError) as exc_info:
        policy.validate_candidate(candidate)
    assert "exceeds maximum allowed limit" in str(exc_info.value)


def test_memory_policy_metadata_size_limit():
    policy = MemoryPolicy(max_metadata_bytes=100)
    candidate = MemoryCandidate(
        content="Normal text",
        metadata={"large_key": "X" * 150},
    )
    with pytest.raises(MemoryPolicyViolationError) as exc_info:
        policy.validate_candidate(candidate)
    assert "exceeds limit" in str(exc_info.value)


def test_memory_policy_ownership_enforcement():
    policy = MemoryPolicy()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # Same user passes
    policy.validate_ownership(user_a, user_a)

    # Different user raises MemoryOwnershipError
    with pytest.raises(MemoryOwnershipError) as exc_info:
        policy.validate_ownership(user_a, user_b)
    assert "different user" in str(exc_info.value)


def test_memory_policy_recency_score_decay():
    policy = MemoryPolicy(recency_decay_seconds=86400.0)  # 1 day decay
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)

    # Brand new memory -> recency ~ 1.0
    rec_now = policy.compute_recency_score(now, reference_time=now)
    assert pytest.approx(rec_now, 0.001) == 1.0

    # 1 day old memory -> recency ~ e^(-1) ~ 0.3678
    past_1d = now - timedelta(days=1)
    rec_1d = policy.compute_recency_score(past_1d, reference_time=now)
    assert 0.35 < rec_1d < 0.38

    # 7 days old -> significantly decayed
    past_7d = now - timedelta(days=7)
    rec_7d = policy.compute_recency_score(past_7d, reference_time=now)
    assert rec_7d < 0.01


def test_memory_policy_final_ranking_score():
    policy = MemoryPolicy(
        weight_similarity=0.6,
        weight_recency=0.2,
        weight_importance=0.2,
    )
    score = policy.compute_final_score(similarity=1.0, recency=1.0, importance=1.0)
    assert pytest.approx(score, 0.001) == 1.0

    score_half = policy.compute_final_score(similarity=0.5, recency=0.5, importance=0.5)
    assert pytest.approx(score_half, 0.001) == 0.5

    # Proving ranking order: higher similarity yields higher score
    high_sim = policy.compute_final_score(similarity=0.9, recency=0.5, importance=0.5)
    low_sim = policy.compute_final_score(similarity=0.2, recency=0.5, importance=0.5)
    assert high_sim > low_sim


def test_memory_policy_invalid_weights_sum():
    with pytest.raises(MemoryPolicyViolationError):
        MemoryPolicy(
            weight_similarity=0.5, weight_recency=0.5, weight_importance=0.5
        )  # Sums to 1.5
