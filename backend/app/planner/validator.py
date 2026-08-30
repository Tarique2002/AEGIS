"""Topological graph validator and security checker for ExecutionPlans."""

from app.core.errors import CyclicDependencyError, PlanValidationError
from app.planner.policies import PlannerPolicy
from app.planner.schemas import (
    ConditionOperator,
    ExecutionPlan,
    NodeType,
    PlanNode,
    TransformOperation,
)
from app.tools.registry import ToolRegistry, create_default_tool_registry


class PlanValidator:
    """
    Validates execution plans for DAG acyclicity, depth boundaries,
    valid dependency references, and safe node configurations.
    """

    def __init__(
        self,
        policy: PlannerPolicy | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.policy = policy or PlannerPolicy()
        self.tool_registry = tool_registry or create_default_tool_registry()

    def validate_plan(self, plan: ExecutionPlan) -> None:
        """
        Perform comprehensive structural, topological, and security validation on a plan.
        Raises PlanValidationError or CyclicDependencyError if invalid.
        """
        nodes = [n for n in plan.nodes if n.enabled]
        self.policy.validate_node_count(len(nodes))

        # 1. Check duplicate node IDs
        node_map: dict[str, PlanNode] = {}
        for node in nodes:
            if node.node_id in node_map:
                raise PlanValidationError(
                    f"Duplicate node_id '{node.node_id}' detected in execution plan."
                )
            node_map[node.node_id] = node

        # 2. Check dependencies exist & no self-dependencies
        for node in nodes:
            if node.node_id in node.dependencies:
                raise CyclicDependencyError(f"Node '{node.node_id}' cannot depend on itself.")
            for dep_id in node.dependencies:
                if dep_id not in node_map:
                    raise PlanValidationError(
                        f"Node '{node.node_id}' references non-existent dependency '{dep_id}'."
                    )

        # 3. Check for single logical FINAL node
        final_nodes = [n for n in nodes if n.node_type == NodeType.FINAL]
        if len(final_nodes) != 1:
            raise PlanValidationError(
                f"Execution plan must contain exactly one FINAL node; found {len(final_nodes)}."
            )

        # 4. Topological sort & cycle detection (Kahn's Algorithm)
        in_degree: dict[str, int] = {n.node_id: len(n.dependencies) for n in nodes}
        adj_list: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for node in nodes:
            for dep in node.dependencies:
                adj_list[dep].append(node.node_id)

        queue: list[str] = [n_id for n_id, deg in in_degree.items() if deg == 0]
        visited_count = 0
        depth_map: dict[str, int] = {n_id: 1 for n_id in queue}

        while queue:
            curr = queue.pop(0)
            visited_count += 1
            curr_depth = depth_map[curr]

            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                depth_map[neighbor] = max(depth_map.get(neighbor, 1), curr_depth + 1)
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(nodes):
            raise CyclicDependencyError("Execution graph contains circular dependency or cycle.")

        max_depth = max(depth_map.values()) if depth_map else 0
        self.policy.validate_depth(max_depth)

        # 5. Validate individual node configurations & security bounds
        for node in nodes:
            self._validate_node_security_and_config(node)

    def _validate_node_security_and_config(self, node: PlanNode) -> None:
        """Validate safety, bounds, and parameters of an individual node."""
        self.policy.validate_retries(node.retry_policy.max_attempts)

        if node.node_type == NodeType.TOOL:
            tool_name = node.configuration.get("tool_name")
            if not tool_name:
                raise PlanValidationError(
                    f"Tool node '{node.node_id}' is missing 'tool_name' in configuration."
                )
            if not self.tool_registry.contains(tool_name):
                raise PlanValidationError(
                    f"Tool node '{node.node_id}' requests unknown tool '{tool_name}'."
                )
            tool_entry = self.tool_registry.get(tool_name)
            if not tool_entry.definition.enabled:
                raise PlanValidationError(
                    f"Tool node '{node.node_id}' requests disabled tool '{tool_name}'."
                )

        elif node.node_type == NodeType.TRANSFORM:
            op_name = node.configuration.get("operation")
            if not op_name:
                raise PlanValidationError(
                    f"Transform node '{node.node_id}' is missing 'operation' in configuration."
                )
            valid_ops = {op.value for op in TransformOperation}
            if op_name not in valid_ops:
                raise PlanValidationError(
                    f"Transform node '{node.node_id}' specifies invalid/unauthorized operation "
                    f"'{op_name}'. Allowed operations: {', '.join(valid_ops)}."
                )

        elif node.node_type == NodeType.CONDITION:
            op_name = node.configuration.get("operator")
            if not op_name:
                raise PlanValidationError(
                    f"Condition node '{node.node_id}' is missing 'operator' in configuration."
                )
            valid_conds = {op.value for op in ConditionOperator}
            if op_name not in valid_conds:
                raise PlanValidationError(
                    f"Condition node '{node.node_id}' specifies invalid operator '{op_name}'. "
                    f"Allowed operators: {', '.join(valid_conds)}."
                )
