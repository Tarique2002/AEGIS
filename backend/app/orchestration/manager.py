"""MultiAgentManager coordinating high-level agent workers and delegation strategies."""

from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import (
    WorkerDefinition,
    WorkerType,
)
from app.orchestration.worker import WorkerRegistry


class MultiAgentManager:
    """Manager coordinating specialized worker definitions and orchestration strategies."""

    def __init__(
        self,
        registry: WorkerRegistry | None = None,
        policy: OrchestrationPolicy | None = None,
    ) -> None:
        self.registry = registry or WorkerRegistry()
        self.policy = policy or OrchestrationPolicy()

    def list_available_workers(self) -> list[WorkerDefinition]:
        """List all registered worker agent specifications."""
        return [self.registry.get_by_type(wt) for wt in WorkerType]

    def register_custom_worker(self, worker_def: WorkerDefinition) -> None:
        """Register a custom worker within configured safety policy bounds."""
        self.registry._workers[worker_def.worker_id] = worker_def
