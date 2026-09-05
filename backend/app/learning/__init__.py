"""Self-Learning & Agent Evolution Engine (Phase 11)."""

from app.learning.evaluator import OutcomeEvaluator
from app.learning.promotion import PromotionManager, PromotionPolicy
from app.learning.sanitizer import sanitize_data
from app.learning.schemas import (
    ExecutionTrajectory,
    LearnedProcedure,
    LearningSignal,
    LearningSignalType,
    OutcomeEvaluationResult,
    ProcedureCandidate,
    ProcedurePromotionDecision,
    PromotionStatus,
    StrategyRecommendation,
    StrategyRecommendationQuery,
    StrategyRecommendationResponse,
    TrajectoryCreate,
)
from app.learning.service import SelfLearningService
from app.learning.strategy import StrategySelector

__all__ = [
    "SelfLearningService",
    "OutcomeEvaluator",
    "PromotionManager",
    "PromotionPolicy",
    "StrategySelector",
    "sanitize_data",
    "ExecutionTrajectory",
    "TrajectoryCreate",
    "OutcomeEvaluationResult",
    "LearningSignal",
    "LearningSignalType",
    "LearnedProcedure",
    "ProcedureCandidate",
    "ProcedurePromotionDecision",
    "PromotionStatus",
    "StrategyRecommendation",
    "StrategyRecommendationQuery",
    "StrategyRecommendationResponse",
]
