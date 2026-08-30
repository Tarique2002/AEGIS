"""Unit tests for planner schemas, node models, and status lifecycle."""

import uuid

import pytest
from app.planner.schemas import (
    ConditionOperator,
    ExecutionContext,
    ExecutionPlan,
    NodeStatus,
    NodeType,
    PlanNode,
    PlanStatus,
    RetryPolicy,
    TransformOperation,
)
from pydantic import ValidationError


def test_plan_node_schema_valid() -> None:
    node = PlanNode(
        node_id="calc_1",
        node_type=NodeType.TOOL,
        name="Calculator 1",
        description="Run calculation",
        dependencies=[],
        input_mapping={},
        output_key="calc_1_out",
        configuration={"tool_name": "calculator"},
        timeout_seconds=30.0,
        retry_policy=RetryPolicy(max_attempts=2),
    )
    assert node.node_id == "calc_1"
    assert node.node_type == NodeType.TOOL
    assert node.retry_policy.max_attempts == 2


def test_plan_node_invalid_timeout_and_retries() -> None:
    with pytest.raises(ValidationError):
        PlanNode(
            node_id="invalid",
            node_type=NodeType.TOOL,
            name="Invalid",
            timeout_seconds=0.5,  # Must be >= 1.0
        )

    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=20)  # Must be <= 10


def test_execution_plan_schema_valid() -> None:
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plan = ExecutionPlan(
        task_id=task_id,
        run_id=run_id,
        objective="Calculate 10 * 5",
        nodes=[
            PlanNode(
                node_id="n1",
                node_type=NodeType.TOOL,
                name="Calc",
                configuration={"tool_name": "calculator"},
            ),
            PlanNode(
                node_id="n2",
                node_type=NodeType.FINAL,
                name="Final",
                dependencies=["n1"],
            ),
        ],
        status=PlanStatus.VALIDATED,
    )
    assert plan.status == PlanStatus.VALIDATED
    assert len(plan.nodes) == 2


def test_transform_and_condition_allowlists() -> None:
    assert TransformOperation.FORMAT_TEXT.value == "format_text"
    assert TransformOperation.SELECT_FIELD.value == "select_field"
    assert ConditionOperator.GREATER_THAN.value == "greater_than"
    assert ConditionOperator.EQUALS.value == "equals"


def test_execution_context_schema() -> None:
    ctx = ExecutionContext(
        task_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        node_outputs={"n1": 50},
        node_statuses={"n1": NodeStatus.COMPLETED},
        variables={"x": 10},
    )
    assert ctx.node_outputs["n1"] == 50
    assert ctx.node_statuses["n1"] == NodeStatus.COMPLETED
