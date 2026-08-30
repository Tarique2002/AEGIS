"""Unit tests for Memory schemas and models."""

import uuid

from app.memory.schemas import (
    EpisodicMemoryRecord,
    MemoryCandidate,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryStatus,
    MemoryType,
    ProceduralMemoryRecord,
)


def test_memory_record_creation_and_defaults():
    user_id = uuid.uuid4()
    record = MemoryRecord(
        memory_type=MemoryType.SEMANTIC,
        user_id=user_id,
        content="Important semantic context",
        importance=0.8,
    )
    assert record.memory_id is not None
    assert record.memory_type == MemoryType.SEMANTIC
    assert record.user_id == user_id
    assert record.content == "Important semantic context"
    assert record.importance == 0.8
    assert record.status == MemoryStatus.ACTIVE
    assert record.created_at is not None
    assert record.updated_at is not None


def test_memory_candidate_defaults():
    candidate = MemoryCandidate(content="Candidate memory text")
    assert candidate.memory_type == MemoryType.SEMANTIC
    assert candidate.importance == 0.5
    assert candidate.metadata == {}


def test_procedural_memory_record():
    user_id = uuid.uuid4()
    proc = ProceduralMemoryRecord(
        name="CSV Analysis",
        description="Standard step-by-step procedure for analyzing CSV files",
        steps=[
            {"step": 1, "action": "inspect_headers"},
            {"step": 2, "action": "compute_aggregates"},
        ],
        user_id=user_id,
    )
    assert proc.procedure_id is not None
    assert proc.version == 1
    assert len(proc.steps) == 2


def test_episodic_memory_record():
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    episode = EpisodicMemoryRecord(
        user_id=user_id,
        task_id=task_id,
        run_id=run_id,
        objective="Analyze quarterly metrics",
        summary="Successfully extracted and summarized quarterly financial trends.",
        actions=[{"tool": "calculator", "args": {"expression": "100 * 5"}}],
        observations=[{"output": 500}],
        result={"final_status": "success"},
    )
    assert episode.episode_id is not None
    assert episode.status == "completed"
    assert episode.importance == 0.5


def test_memory_search_query_and_result():
    query = MemorySearchQuery(query_text="financial report", limit=10, min_score=0.7)
    assert query.limit == 10
    assert query.min_score == 0.7

    rec = MemoryRecord(
        memory_type=MemoryType.SEMANTIC,
        user_id=uuid.uuid4(),
        content="Financial Q3 report summary",
    )
    res = MemorySearchResult(
        record=rec,
        score=0.85,
        matched_by="semantic_vector",
        similarity_score=0.9,
        recency_score=0.8,
        importance_score=0.85,
    )
    assert res.score == 0.85
    assert res.matched_by == "semantic_vector"
