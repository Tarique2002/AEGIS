"""Security policy, ownership validation, and retrieval ranking logic for memory operations."""

import json
import math
import uuid
from datetime import datetime

from app.memory.errors import (
    MemoryOwnershipError,
    MemoryPolicyViolationError,
    MemoryValidationError,
)
from app.memory.schemas import MemoryCandidate
from app.schemas.common import utc_now


class MemoryPolicy:
    """
    Security gate that validates memory limits, user ownership,
    and calculates normalized multi-factor retrieval scores.
    """

    def __init__(
        self,
        max_content_length: int = 10000,
        max_metadata_bytes: int = 32768,
        max_retrieval_limit: int = 50,
        default_working_ttl: int = 3600,
        semantic_dedup_threshold: float = 0.95,
        weight_similarity: float = 0.6,
        weight_recency: float = 0.2,
        weight_importance: float = 0.2,
        recency_decay_seconds: float = 7 * 86400.0,  # 7-day half-life
    ) -> None:
        self.max_content_length = max_content_length
        self.max_metadata_bytes = max_metadata_bytes
        self.max_retrieval_limit = max_retrieval_limit
        self.default_working_ttl = default_working_ttl
        self.semantic_dedup_threshold = semantic_dedup_threshold

        # Validate weights sum and bounds
        if not (
            0.0 <= weight_similarity <= 1.0
            and 0.0 <= weight_recency <= 1.0
            and 0.0 <= weight_importance <= 1.0
        ):
            raise MemoryPolicyViolationError("Ranking weights must be in range [0.0, 1.0].")

        total_weight = weight_similarity + weight_recency + weight_importance
        if abs(total_weight - 1.0) > 1e-4:
            raise MemoryPolicyViolationError(
                f"Ranking weights must sum to 1.0 (got {total_weight:.3f})."
            )

        self.weight_similarity = weight_similarity
        self.weight_recency = weight_recency
        self.weight_importance = weight_importance
        self.recency_decay_seconds = recency_decay_seconds

    def validate_candidate(self, candidate: MemoryCandidate) -> None:
        """Validate candidate payload size, importance bounds, and metadata."""
        if not candidate.content or not candidate.content.strip():
            raise MemoryValidationError("Memory content cannot be empty.")

        if len(candidate.content) > self.max_content_length:
            raise MemoryPolicyViolationError(
                f"Memory content size ({len(candidate.content)}) exceeds maximum "
                f"allowed limit of {self.max_content_length} characters.",
                details={
                    "content_length": len(candidate.content),
                    "limit": self.max_content_length,
                },
            )

        if not (0.0 <= candidate.importance <= 1.0):
            raise MemoryValidationError(
                f"Importance score must be between 0.0 and 1.0 (got {candidate.importance})."
            )

        try:
            metadata_size = len(json.dumps(candidate.metadata).encode("utf-8"))
            if metadata_size > self.max_metadata_bytes:
                raise MemoryPolicyViolationError(
                    f"Memory metadata size ({metadata_size} bytes) exceeds limit of "
                    f"{self.max_metadata_bytes} bytes.",
                    details={"metadata_bytes": metadata_size, "limit": self.max_metadata_bytes},
                )
        except (TypeError, ValueError) as exc:
            raise MemoryValidationError(f"Unserializable metadata: {str(exc)}") from exc

    def validate_ownership(
        self,
        record_user_id: uuid.UUID | str,
        trusted_context_user_id: uuid.UUID | str,
    ) -> None:
        """Enforce strict cross-user ownership isolation."""
        if str(record_user_id) != str(trusted_context_user_id):
            raise MemoryOwnershipError(
                "Access denied: memory item belongs to a different user.",
                details={"requested_user": str(record_user_id)},
            )

    def compute_recency_score(
        self,
        created_at: datetime,
        reference_time: datetime | None = None,
    ) -> float:
        """
        Deterministic exponential decay recency score in range (0.0, 1.0].
        Newer memories yield values closer to 1.0.
        """
        now = reference_time or utc_now()
        age_seconds = max(0.0, (now - created_at).total_seconds())
        # e^(-age / decay)
        score = math.exp(-age_seconds / self.recency_decay_seconds)
        return min(1.0, max(0.0, score))

    def compute_final_score(
        self,
        similarity: float,
        recency: float,
        importance: float,
    ) -> float:
        """
        Calculate normalized multi-factor retrieval rank:
        FinalScore = w_sim * Similarity + w_rec * Recency + w_imp * Importance
        """
        sim_norm = min(1.0, max(0.0, similarity))
        rec_norm = min(1.0, max(0.0, recency))
        imp_norm = min(1.0, max(0.0, importance))

        final_score = (
            self.weight_similarity * sim_norm
            + self.weight_recency * rec_norm
            + self.weight_importance * imp_norm
        )
        return min(1.0, max(0.0, final_score))
