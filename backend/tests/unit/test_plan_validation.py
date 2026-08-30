"""Unit tests for PlanValidator, topological DAG sorting, and boundary checks."""

import uuid

import pytest
from app.core.errors import CyclicDependencyError, PlanValidationError
from app.planner.policies import PlannerPolicy
from app.planner.schemas import ExecutionPlan, NodeType, PlanNode
from app.planner.validator import PlanValidator


def _create_base_plan(nodes: list[PlanNode]) -> ExecutionPlan:
    return ExecutionPlan(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        objective="Test objective",
        nodes=nodes,
    )


def test_validator_valid_linear_plan() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Calc",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="n2",
            node_type=NodeType.TRANSFORM,
            name="Format",
            dependencies=["n1"],
            configuration={"operation": "format_text", "template": "{result}"},
        ),
        PlanNode(
            node_id="n3",
            node_type=NodeType.FINAL,
            name="Final",
            dependencies=["n2"],
        ),
    ]
    plan = _create_base_plan(nodes)
    validator.validate_plan(plan)  # Should not raise


def test_validator_duplicate_node_id() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Calc 1",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Calc 2",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(PlanValidationError, match="Duplicate node_id"):
        validator.validate_plan(plan)


def test_validator_nonexistent_dependency() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Calc",
            configuration={"tool_name": "calculator"},
            dependencies=["missing_node"],
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(PlanValidationError, match="references non-existent dependency"):
        validator.validate_plan(plan)


def test_validator_self_dependency() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Calc",
            configuration={"tool_name": "calculator"},
            dependencies=["n1"],
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(CyclicDependencyError, match="cannot depend on itself"):
        validator.validate_plan(plan)


def test_validator_cycle_detection() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="a",
            node_type=NodeType.TOOL,
            name="A",
            configuration={"tool_name": "calculator"},
            dependencies=["c"],
        ),
        PlanNode(
            node_id="b",
            node_type=NodeType.TOOL,
            name="B",
            configuration={"tool_name": "calculator"},
            dependencies=["a"],
        ),
        PlanNode(
            node_id="c",
            node_type=NodeType.TOOL,
            name="C",
            configuration={"tool_name": "calculator"},
            dependencies=["b"],
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["c"]),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(CyclicDependencyError, match="circular dependency or cycle"):
        validator.validate_plan(plan)


def test_validator_missing_final_node() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Calc",
            configuration={"tool_name": "calculator"},
        ),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(PlanValidationError, match="must contain exactly one FINAL node"):
        validator.validate_plan(plan)


def test_validator_unknown_tool() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="BadTool",
            configuration={"tool_name": "unregistered_tool_xyz"},
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(PlanValidationError, match="requests unknown tool"):
        validator.validate_plan(plan)


def test_validator_unauthorized_transform() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TRANSFORM,
            name="EvalTransform",
            configuration={"operation": "eval_arbitrary_code"},
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(PlanValidationError, match="invalid/unauthorized operation"):
        validator.validate_plan(plan)


def test_validator_max_node_count_exceeded() -> None:
    policy = PlannerPolicy(max_plan_nodes=2)
    validator = PlanValidator(policy=policy)
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="N1",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="n2",
            node_type=NodeType.TOOL,
            name="N2",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1", "n2"]
        ),
    ]
    plan = _create_base_plan(nodes)
    with pytest.raises(PlanValidationError, match="exceeds maximum allowed"):
        validator.validate_plan(plan)
