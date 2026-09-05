"""Strategy selection and ranking engine.
Ranks based on semantic relevance, success rates, and confidence.
"""

import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from app.learning.schemas import (
    LearnedProcedure,
    PromotionStatus,
    StrategyRecommendation,
    StrategyRecommendationQuery,
)


class StrategySelector:
    """
    Ranks learned procedures using composite scoring:
    Score = (relevance * 0.35) + (success_rate * 0.30) + (confidence * 0.20) + (recency * 0.15)
    """

    def rank_procedures(
        self,
        query: StrategyRecommendationQuery,
        procedures: Sequence[LearnedProcedure],
        user_id: uuid.UUID,
    ) -> list[StrategyRecommendation]:
        """
        Filter and rank candidate procedures for the trusted user and objective.
        Strict tenant isolation: procedure must belong to user_id or be explicitly is_global.
        """
        ranked: list[tuple[float, StrategyRecommendation]] = []
        now = datetime.now(UTC)
        query_terms = set(query.objective.lower().split())

        for proc in procedures:
            # 1. Tenant boundary
            if proc.user_id != user_id and not proc.is_global:
                continue

            # 2. Status filter
            if proc.status != PromotionStatus.PROMOTED:
                continue

            # 3. Domain filter (if requested)
            if query.domain and proc.task_domain != "general" and proc.task_domain != query.domain:
                continue

            # 4. Tool compatibility
            if query.available_tools is not None:
                available_set = set(query.available_tools)
                required_set = set(proc.required_tools)
                missing_tools = required_set - available_set
                if missing_tools:
                    # Heavily penalize or skip if missing required tools
                    continue

            # 5. Semantic Relevance (term overlap + trigger match)
            proc_text = (
                f"{proc.name} {proc.description} {' '.join(proc.trigger_conditions)}".lower()
            )
            matching_terms = sum(1 for term in query_terms if term in proc_text)
            term_ratio = matching_terms / max(1, len(query_terms))
            relevance = min(1.0, term_ratio * 1.2)

            # 6. Historical success rate (Laplace smoothed)
            success_rate = proc.historical_success_rate

            # 7. Confidence
            confidence = proc.confidence

            # 8. Recency decay (half-life of 30 days)
            updated_at = proc.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            age_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
            recency = math.exp(-0.023 * age_days)  # ~0.5 at 30 days

            # 9. Composite Match Score
            composite_score = round(
                (relevance * 0.35) + (success_rate * 0.30) + (confidence * 0.20) + (recency * 0.15),
                4,
            )

            rationale = (
                f"Match score {composite_score:.2f} (relevance: {relevance:.2f}, "
                f"historical success: {success_rate:.2%}, confidence: {confidence:.2f})"
            )

            rec = StrategyRecommendation(
                procedure_id=proc.procedure_id,
                name=proc.name,
                description=proc.description,
                ordered_steps=proc.ordered_steps,
                required_tools=proc.required_tools,
                match_score=composite_score,
                success_rate=round(success_rate, 4),
                confidence=round(confidence, 4),
                version=proc.version,
                rationale=rationale,
            )
            ranked.append((composite_score, rec))

        # Sort descending by composite score
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in ranked[: query.limit]]
