"""Directed Acyclic Graph (DAG) runtime representation and dependency management."""

from app.planner.schemas import ExecutionPlan, NodeType, PlanNode


class ExecutionGraph:
    """
    In-memory DAG representation for an ExecutionPlan.
    Calculates ready nodes, dependency resolution, and downstream impact cascades.
    """

    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan
        self.nodes: dict[str, PlanNode] = {n.node_id: n for n in plan.nodes if n.enabled}
        self.dependencies: dict[str, set[str]] = {
            n.node_id: set(n.dependencies) for n in self.nodes.values()
        }
        self.dependents: dict[str, set[str]] = {n_id: set() for n_id in self.nodes}
        for n_id, deps in self.dependencies.items():
            for dep in deps:
                if dep in self.dependents:
                    self.dependents[dep].add(n_id)

    def get_ready_nodes(
        self,
        completed_nodes: set[str],
        running_nodes: set[str],
        failed_nodes: set[str],
        skipped_nodes: set[str],
    ) -> list[PlanNode]:
        """
        Identify nodes whose dependencies are all satisfied and are ready for execution.
        """
        ready: list[PlanNode] = []
        handled_nodes = completed_nodes | running_nodes | failed_nodes | skipped_nodes

        for node_id, node in self.nodes.items():
            if node_id in handled_nodes:
                continue

            node_deps = self.dependencies[node_id]
            # Node is ready if all its dependencies are completed
            if node_deps.issubset(completed_nodes):
                ready.append(node)

        return ready

    def get_downstream_dependents(self, failed_node_id: str) -> set[str]:
        """
        Compute all transitive downstream dependent nodes that must be skipped or halted.
        """
        downstream: set[str] = set()
        queue: list[str] = list(self.dependents.get(failed_node_id, set()))

        while queue:
            curr = queue.pop(0)
            if curr not in downstream:
                downstream.add(curr)
                queue.extend(self.dependents.get(curr, set()))

        return downstream

    def get_final_node(self) -> PlanNode | None:
        """Retrieve the designated FINAL node of the graph."""
        for node in self.nodes.values():
            if node.node_type == NodeType.FINAL:
                return node
        return None
