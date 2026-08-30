"""Planner configuration policies, execution bounds, and safety limits."""

from app.core.errors import PlanValidationError


class PlannerPolicy:
    """
    Centralized configuration policy defining strict upper limits and execution constraints.
    Prevents recursive plan explosions, unbounded graph depths, and infinite loops.
    """

    DEFAULT_MAX_PLAN_NODES: int = 30
    DEFAULT_MAX_PLAN_DEPTH: int = 10
    DEFAULT_MAX_PARALLEL_NODES: int = 5
    DEFAULT_MAX_TOTAL_EXECUTION_SECONDS: float = 300.0
    DEFAULT_MAX_RETRIES_PER_NODE: int = 3

    def __init__(
        self,
        max_plan_nodes: int = DEFAULT_MAX_PLAN_NODES,
        max_plan_depth: int = DEFAULT_MAX_PLAN_DEPTH,
        max_parallel_nodes: int = DEFAULT_MAX_PARALLEL_NODES,
        max_total_execution_seconds: float = DEFAULT_MAX_TOTAL_EXECUTION_SECONDS,
        max_retries_per_node: int = DEFAULT_MAX_RETRIES_PER_NODE,
    ) -> None:
        self.max_plan_nodes = max_plan_nodes
        self.max_plan_depth = max_plan_depth
        self.max_parallel_nodes = max_parallel_nodes
        self.max_total_execution_seconds = max_total_execution_seconds
        self.max_retries_per_node = max_retries_per_node

    def validate_node_count(self, count: int) -> None:
        """Validate that total node count is within safe limits."""
        if count <= 0:
            raise PlanValidationError("Execution plan must contain at least 1 node.")
        if count > self.max_plan_nodes:
            raise PlanValidationError(
                f"Plan node count ({count}) exceeds maximum allowed ({self.max_plan_nodes})."
            )

    def validate_depth(self, depth: int) -> None:
        """Validate that DAG topological depth is within safe limits."""
        if depth > self.max_plan_depth:
            raise PlanValidationError(
                f"Plan DAG depth ({depth}) exceeds maximum permitted depth ({self.max_plan_depth})."
            )

    def validate_retries(self, retries: int) -> None:
        """Validate that node retry count is within bounded limits."""
        if retries < 0 or retries > self.max_retries_per_node:
            raise PlanValidationError(
                f"Node retries ({retries}) exceeds max allowed ({self.max_retries_per_node})."
            )
