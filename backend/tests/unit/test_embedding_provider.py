"""Unit tests for EmbeddingProvider abstractions and deterministic MockEmbeddingProvider."""

import math

import pytest
from app.memory.semantic.embeddings import MockEmbeddingProvider


@pytest.mark.asyncio
async def test_mock_embedding_provider_determinism():
    provider = MockEmbeddingProvider(dimension=384)
    text = "Machine learning and natural language processing in AEGIS"

    vec1 = await provider.embed(text)
    vec2 = await provider.embed(text)

    assert len(vec1) == 384
    assert len(vec2) == 384
    assert vec1 == vec2  # Exact deterministic match


@pytest.mark.asyncio
async def test_mock_embedding_provider_unit_normalization():
    provider = MockEmbeddingProvider(dimension=128)
    vec = await provider.embed("Vector normalization verification text")

    norm = math.sqrt(sum(x * x for x in vec))
    assert pytest.approx(norm, 0.001) == 1.0


@pytest.mark.asyncio
async def test_mock_embedding_provider_batch():
    provider = MockEmbeddingProvider(dimension=64)
    texts = ["First prompt", "Second prompt", "Third prompt"]

    vectors = await provider.embed_batch(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 64


def test_mock_embedding_provider_metadata():
    provider = MockEmbeddingProvider(dimension=384)
    meta = provider.metadata()
    assert meta["provider"] == "mock"
    assert meta["dimension"] == 384
    assert meta["deterministic"] is True
