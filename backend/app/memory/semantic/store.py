"""Qdrant-backed Semantic Memory Store with strict user isolation and deduplication."""

import hashlib
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.db.qdrant import get_qdrant_client
from app.memory.base import BaseMemoryStore
from app.memory.errors import MemoryStorageError
from app.memory.policies import MemoryPolicy
from app.memory.schemas import (
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryStatus,
    MemoryType,
)
from app.memory.semantic.embeddings import EmbeddingProvider, MockEmbeddingProvider


class SemanticMemoryStore(BaseMemoryStore):
    """
    Semantic Memory Store backed by Qdrant vector database.
    Provides vector storage, ownership-scoped vector search, and two-stage deduplication.
    """

    COLLECTION_NAME = "aegis_semantic_memory"

    def __init__(
        self,
        qdrant_client: AsyncQdrantClient | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        policy: MemoryPolicy | None = None,
    ) -> None:
        self._client = qdrant_client
        self.embedding_provider = embedding_provider or MockEmbeddingProvider()
        self.policy = policy or MemoryPolicy()
        self._collection_initialized = False

    @property
    def client(self) -> AsyncQdrantClient:
        """Get the active Qdrant client instance."""
        if self._client is None:
            self._client = get_qdrant_client()
        return self._client

    @property
    def memory_type(self) -> MemoryType:
        return MemoryType.SEMANTIC

    async def ensure_collection_exists(self) -> None:
        """Ensure the Qdrant vector collection is created with proper vector configuration."""
        if self._collection_initialized:
            return

        try:
            collections = await self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            if self.COLLECTION_NAME not in collection_names:
                await self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=qmodels.VectorParams(
                        size=self.embedding_provider.dimension,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
            self._collection_initialized = True
        except Exception as exc:
            # If Qdrant is unavailable, log or handle gracefully
            raise MemoryStorageError(f"Failed to initialize Qdrant collection: {exc}") from exc

    async def find_duplicate(
        self,
        content: str,
        user_id: uuid.UUID,
        threshold: float | None = None,
    ) -> MemoryRecord | None:
        """
        Two-stage deduplication:
        1. Exact content hash match.
        2. Semantic similarity search exceeding threshold.
        """
        await self.ensure_collection_exists()
        dedup_threshold = (
            threshold if threshold is not None else self.policy.semantic_dedup_threshold
        )

        content_clean = content.strip().lower()
        content_hash = hashlib.sha256(content_clean.encode("utf-8")).hexdigest()

        # Stage 1: Exact hash filter
        try:
            exact_matches = await self.client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="user_id",
                            match=qmodels.MatchValue(value=str(user_id)),
                        ),
                        qmodels.FieldCondition(
                            key="content_hash",
                            match=qmodels.MatchValue(value=content_hash),
                        ),
                    ]
                ),
                limit=1,
            )
            if exact_matches and exact_matches[0]:
                payload = exact_matches[0][0].payload
                if payload:
                    return MemoryRecord.model_validate(payload)
        except Exception:
            pass

        # Stage 2: Semantic vector similarity search
        try:
            vector = await self.embedding_provider.embed(content)
            search_results = await self.client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=vector,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="user_id",
                            match=qmodels.MatchValue(value=str(user_id)),
                        ),
                    ]
                ),
                limit=1,
                score_threshold=dedup_threshold,
            )
            if search_results:
                top = search_results[0]
                if top.payload:
                    return MemoryRecord.model_validate(top.payload)
        except Exception as exc:
            raise MemoryStorageError(f"Failed during semantic deduplication check: {exc}") from exc

        return None

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        """Embed and upsert memory record into Qdrant."""
        await self.ensure_collection_exists()

        content_clean = record.content.strip().lower()
        content_hash = hashlib.sha256(content_clean.encode("utf-8")).hexdigest()

        try:
            vector = await self.embedding_provider.embed(record.content)
            payload = record.model_dump(mode="json")
            payload["content_hash"] = content_hash

            point = qmodels.PointStruct(
                id=str(record.memory_id),
                vector=vector,
                payload=payload,
            )

            await self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[point],
            )
            return record
        except Exception as exc:
            raise MemoryStorageError(
                f"Failed to upsert semantic memory into Qdrant: {exc}"
            ) from exc

    async def get(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MemoryRecord | None:
        """Retrieve a semantic memory record by ID with user isolation."""
        await self.ensure_collection_exists()
        try:
            points = await self.client.retrieve(
                collection_name=self.COLLECTION_NAME,
                ids=[str(memory_id)],
                with_payload=True,
            )
            if not points:
                return None

            payload = points[0].payload
            if not payload:
                return None

            # Enforce user isolation
            if str(payload.get("user_id")) != str(user_id):
                return None

            return MemoryRecord.model_validate(payload)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to retrieve semantic memory: {exc}") from exc

    async def delete(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete semantic memory record by ID with user isolation."""
        await self.ensure_collection_exists()
        # Verify ownership first
        existing = await self.get(memory_id, user_id)
        if not existing:
            return False

        try:
            await self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=qmodels.PointIdsList(points=[str(memory_id)]),
            )
            return True
        except Exception as exc:
            raise MemoryStorageError(f"Failed to delete semantic memory: {exc}") from exc

    async def search(
        self,
        query: MemorySearchQuery,
    ) -> list[MemorySearchResult]:
        """Search semantic memories using vector similarity and strict user isolation."""
        user_id = query.user_id
        if not user_id:
            return []

        await self.ensure_collection_exists()
        try:
            vector = await self.embedding_provider.embed(query.query_text)

            # Mandatory ownership filter
            filter_conditions: list[Any] = [
                qmodels.FieldCondition(
                    key="user_id",
                    match=qmodels.MatchValue(value=str(user_id)),
                ),
                qmodels.FieldCondition(
                    key="status",
                    match=qmodels.MatchValue(value=MemoryStatus.ACTIVE.value),
                ),
            ]

            scored_points = await self.client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=vector,
                query_filter=qmodels.Filter(must=filter_conditions),
                limit=query.limit,
                score_threshold=query.min_score,
            )

            results: list[MemorySearchResult] = []
            for sp in scored_points:
                if not sp.payload:
                    continue
                rec = MemoryRecord.model_validate(sp.payload)
                # Normalize cosine similarity (Qdrant cosine is in [-1, 1], normalized to [0, 1])
                similarity_norm = max(
                    0.0, min(1.0, (sp.score + 1.0) / 2.0 if sp.score <= 1.0 else sp.score)
                )
                recency_norm = self.policy.compute_recency_score(rec.created_at)
                final_score = self.policy.compute_final_score(
                    similarity=similarity_norm,
                    recency=recency_norm,
                    importance=rec.importance,
                )

                results.append(
                    MemorySearchResult(
                        record=rec,
                        score=final_score,
                        matched_by="semantic_vector",
                        similarity_score=similarity_norm,
                        recency_score=recency_norm,
                        importance_score=rec.importance,
                    )
                )

            # Sort by combined multi-factor rank
            results.sort(key=lambda r: r.score, reverse=True)
            return results[: query.limit]
        except Exception as exc:
            raise MemoryStorageError(f"Failed to search semantic memory: {exc}") from exc
