"""FastAPI dependency providers for Multi-Agent Orchestration components."""

from app.orchestration.service import OrchestrationService


def get_orchestration_service() -> OrchestrationService:
    """Dependency provider returning an instantiated OrchestrationService."""
    return OrchestrationService()
