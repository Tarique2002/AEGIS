"""Embedding provider abstractions and deterministic mock implementations."""

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ExternalServiceError


class EmbeddingProvider(ABC):
    """Abstract interface for generating vector embeddings."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimensionality."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a list of texts."""
        ...

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Return provider metadata."""
        ...


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic mock embedding provider for tests and local development.
    Guarantees that the same text always yields the identical unit vector.
    Uses token-hashing to produce meaningful semantic dot products for similar texts.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "mock",
            "model": "mock-embeddings-v1",
            "dimension": self._dimension,
            "deterministic": True,
        }

    def _generate_vector(self, text: str) -> list[float]:
        cleaned = text.strip().lower()
        if not cleaned:
            return [0.0] * self._dimension

        vec = [0.0] * self._dimension
        words = cleaned.split()

        for word in words:
            # Deterministic hash to dimension bucket
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dimension
            sign = 1.0 if (h >> 4) % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 + (len(word) / 10.0))

        # Also add whole string hash distribution
        full_hash = int(hashlib.sha256(cleaned.encode("utf-8")).hexdigest(), 16)
        for i in range(min(16, self._dimension)):
            bucket = (full_hash + i * 31) % self._dimension
            vec[bucket] += 0.5

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return [0.0] * self._dimension
        return [x / norm for x in vec]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider connecting to Ollama's /api/embeddings endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "nomic-embed-text",
        dimension: int = 768,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model
        self._dimension = dimension
        self.timeout_seconds = timeout_seconds

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for text in texts:
                try:
                    response = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                    if response.status_code != 200:
                        raise ExternalServiceError(
                            f"Ollama embedding request failed: HTTP {response.status_code}",
                            details={"status_code": response.status_code, "body": response.text},
                        )
                    data = response.json()
                    embedding = data.get("embedding", [])
                    results.append(embedding)
                except httpx.RequestError as exc:
                    raise ExternalServiceError(
                        f"Failed to connect to Ollama embedding service: {exc}"
                    ) from exc
        return results

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "model": self.model,
            "dimension": self._dimension,
            "base_url": self.base_url,
        }
