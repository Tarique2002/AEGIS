"""Delegation planner, DAG validation, depth checking, and cycle detection."""

import uuid
from collections import defaultdict, deque

from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.orchestration.errors import CircularDelegationError, DelegationPlanError
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import (
    DelegatedTask,
    DelegationExecutionMode,
    DelegationPlan,
    WorkerType,
)

logger = get_logger(__name__)


class DelegationPlanner:
    """Decomposes an objective into a typed, validated dependency graph of worker tasks."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        policy: OrchestrationPolicy | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.policy = policy or OrchestrationPolicy()

    def create_heuristic_plan(
        self,
        orchestration_id: uuid.UUID,
        objective: str,
        custom_tasks: list[DelegatedTask] | None = None,
        execution_mode: DelegationExecutionMode = DelegationExecutionMode.DEPENDENCY_GRAPH,
        max_parallel_workers: int = 3,
    ) -> DelegationPlan:
        """Create and validate a delegation plan."""
        if custom_tasks:
            tasks = custom_tasks
        else:
            tasks = self._generate_default_tasks(objective)

        plan = DelegationPlan(
            orchestration_id=orchestration_id,
            objective=objective,
            tasks=tasks,
            execution_mode=execution_mode,
            max_parallel_workers=max_parallel_workers,
        )

        self.validate_plan(plan)
        return plan

    def _generate_default_tasks(self, objective: str) -> list[DelegatedTask]:
        """Generate canonical multi-worker pipeline based on objective semantics."""
        obj_lower = objective.lower()

        # Quantitative / arithmetic tasks -> Analysis + Verification + Synthesis
        if any(w in obj_lower for w in ["calculate", "number", "sum", "math", "+", "-", "*", "/"]):
            task_analysis = DelegatedTask(
                delegated_task_id="task_analysis",
                worker_id="worker_analysis",
                worker_type=WorkerType.ANALYSIS,
                title="Perform Quantitative Calculation",
                objective=f"Compute numerical results for: {objective}",
                expected_output="Computed numeric calculations and intermediate steps.",
                dependencies=[],
                priority=1,
            )
            task_verify = DelegatedTask(
                delegated_task_id="task_verify",
                worker_id="worker_analysis",
                worker_type=WorkerType.ANALYSIS,
                title="Verify Calculation Independence",
                objective=f"Perform independent verification of calculation for: {objective}",
                expected_output="Independent verification results.",
                dependencies=[],
                priority=1,
            )
            task_synthesis = DelegatedTask(
                delegated_task_id="task_synthesis",
                worker_id="worker_synthesis",
                worker_type=WorkerType.SYNTHESIS,
                title="Synthesize Calculation Outcome",
                objective="Combine calculation and verification findings into final answer.",
                expected_output="Final synthesized mathematical conclusion.",
                dependencies=["task_analysis", "task_verify"],
                priority=2,
            )
            return [task_analysis, task_verify, task_synthesis]

        # Standard pipeline -> Research -> Analysis -> Synthesis
        task_research = DelegatedTask(
            delegated_task_id="task_research",
            worker_id="worker_research",
            worker_type=WorkerType.RESEARCH,
            title="Gather Research & Context",
            objective=f"Retrieve facts, background data, and relevant context for: {objective}",
            expected_output="Collected background research and factual findings.",
            dependencies=[],
            priority=1,
        )
        task_analysis = DelegatedTask(
            delegated_task_id="task_analysis",
            worker_id="worker_analysis",
            worker_type=WorkerType.ANALYSIS,
            title="Analyze Gathered Research",
            objective="Analyze the findings and extract core insights.",
            expected_output="Detailed analytical insights.",
            dependencies=["task_research"],
            priority=2,
        )
        task_synthesis = DelegatedTask(
            delegated_task_id="task_synthesis",
            worker_id="worker_synthesis",
            worker_type=WorkerType.SYNTHESIS,
            title="Synthesize Final Response",
            objective="Synthesize analyzed insights into clear, actionable final output.",
            expected_output="Comprehensive final report.",
            dependencies=["task_analysis"],
            priority=3,
        )
        return [task_research, task_analysis, task_synthesis]

    def validate_plan(self, plan: DelegationPlan) -> None:
        """
        Enforce structural rules:
        1. Task count within policy bounds (<= max_workers).
        2. Unique task IDs.
        3. All dependency references exist and are not self-referential.
        4. Dependency graph is acyclic (Kahn's algorithm).
        5. Dependency depth does not exceed max_dependency_depth.
        """
        tasks = plan.tasks
        if not tasks:
            raise DelegationPlanError("Delegation plan must contain at least one task.")

        if len(tasks) > self.policy.max_workers:
            raise DelegationPlanError(
                f"Delegation plan exceeds maximum allowed workers "
                f"({len(tasks)} > {self.policy.max_workers})."
            )

        task_id_set = {t.delegated_task_id for t in tasks}
        if len(task_id_set) != len(tasks):
            raise DelegationPlanError("Duplicate task IDs detected in delegation plan.")

        # Build in-degrees and adjacency
        in_degree: dict[str, int] = {t.delegated_task_id: 0 for t in tasks}
        adj: dict[str, list[str]] = defaultdict(list)

        for t in tasks:
            for dep in t.dependencies:
                if dep == t.delegated_task_id:
                    raise CircularDelegationError(
                        f"Task '{t.delegated_task_id}' cannot depend on itself."
                    )
                if dep not in task_id_set:
                    raise DelegationPlanError(
                        f"Task '{t.delegated_task_id}' depends on non-existent task '{dep}'."
                    )
                adj[dep].append(t.delegated_task_id)
                in_degree[t.delegated_task_id] += 1

        # Kahn's algorithm for cycle detection
        queue: deque[str] = deque([tid for tid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(tasks):
            raise CircularDelegationError(
                "Circular dependency detected in delegation plan execution DAG."
            )

        # Verify max dependency depth
        depth = self._calculate_max_depth(tasks)
        if depth > self.policy.max_dependency_depth:
            raise DelegationPlanError(
                f"Delegation plan dependency depth ({depth}) exceeds maximum allowed "
                f"({self.policy.max_dependency_depth})."
            )

        logger.info(
            f"Delegation plan '{plan.plan_id}' validated successfully: "
            f"{len(tasks)} tasks, depth {depth}."
        )

    def _calculate_max_depth(self, tasks: list[DelegatedTask]) -> int:
        """Calculate the longest path in the DAG."""
        task_map = {t.delegated_task_id: t for t in tasks}
        memo: dict[str, int] = {}

        def get_depth(task_id: str) -> int:
            if task_id in memo:
                return memo[task_id]
            task = task_map[task_id]
            if not task.dependencies:
                memo[task_id] = 1
                return 1
            max_d = 1 + max(get_depth(d) for d in task.dependencies)
            memo[task_id] = max_d
            return max_d

        return max((get_depth(t.delegated_task_id) for t in tasks), default=0)
