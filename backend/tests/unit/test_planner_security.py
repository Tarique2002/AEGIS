"""Unit tests for planner security boundaries and injection prevention."""

import uuid

import pytest
from app.core.errors import PlanValidationError
from app.planner.schemas import ExecutionPlan, NodeType, PlanNode
from app.planner.validator import PlanValidator


def test_planner_rejects_arbitrary_shell_command_injection() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TOOL,
            name="Shell Attempt",
            configuration={"tool_name": "bash", "arguments": {"cmd": "rm -rf /"}},
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = ExecutionPlan(
        task_id=uuid.uuid4(), run_id=uuid.uuid4(), objective="shell injection", nodes=nodes
    )

    with pytest.raises(PlanValidationError, match="requests unknown tool"):
        validator.validate_plan(plan)


def test_planner_rejects_eval_transform_injection() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.TRANSFORM,
            name="Eval Attack",
            configuration={"operation": "eval_code", "code": "__import__('os').system('ls')"},
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = ExecutionPlan(
        task_id=uuid.uuid4(), run_id=uuid.uuid4(), objective="eval attack", nodes=nodes
    )

    with pytest.raises(PlanValidationError, match="invalid/unauthorized operation"):
        validator.validate_plan(plan)


def test_planner_rejects_unsupported_condition_operator() -> None:
    validator = PlanValidator()
    nodes = [
        PlanNode(
            node_id="n1",
            node_type=NodeType.CONDITION,
            name="Custom Lambda Condition",
            configuration={"operator": "lambda_expr", "code": "lambda x: True"},
        ),
        PlanNode(node_id="n_final", node_type=NodeType.FINAL, name="Final", dependencies=["n1"]),
    ]
    plan = ExecutionPlan(
        task_id=uuid.uuid4(), run_id=uuid.uuid4(), objective="condition injection", nodes=nodes
    )

    with pytest.raises(PlanValidationError, match="invalid operator"):
        validator.validate_plan(plan)
