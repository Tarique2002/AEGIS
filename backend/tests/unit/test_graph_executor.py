"""Unit tests for GraphExecutor, parallel concurrency, and node execution."""

import uuid

import pytest
from app.db.models.plan import ExecutionPlanModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.planner.executor import GraphExecutor
from app.planner.schemas import (
    ExecutionContext,
    ExecutionPlan,
    NodeType,
    PlanNode,
    PlanStatus,
    RetryPolicy,
    TransformOperation,
)
from app.schemas.common import utc_now
from app.tools.service import ToolService
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_task_and_plan(
    session: AsyncSession,
    task_id: uuid.UUID,
    run_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> None:
    task = Task(id=task_id, objective="Test", status="running", task_metadata={})
    run = AgentRun(
        id=run_id,
        task_id=task_id,
        run_type="PLANNING",
        status="running",
        started_at=utc_now(),
    )
    plan_model = ExecutionPlanModel(
        id=plan_id,
        task_id=task_id,
        run_id=run_id,
        objective="Test plan",
        version=1,
        status="RUNNING",
        graph={},
        plan_metadata={},
    )
    session.add(task)
    session.add(run)
    session.add(plan_model)
    await session.commit()


@pytest.mark.asyncio
async def test_graph_executor_linear_calculation(db_session: AsyncSession) -> None:
    executor = GraphExecutor(tool_service=ToolService())

    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    await _seed_task_and_plan(db_session, task_id, run_id, plan_id)

    nodes = [
        PlanNode(
            node_id="node_calc",
            node_type=NodeType.TOOL,
            name="Calculator",
            configuration={"tool_name": "calculator", "arguments": {"expression": "25 * 4"}},
            output_key="calc_out",
        ),
        PlanNode(
            node_id="node_format",
            node_type=NodeType.TRANSFORM,
            name="Format",
            dependencies=["node_calc"],
            input_mapping={"result": "calc_out"},
            output_key="fmt_out",
            configuration={
                "operation": TransformOperation.FORMAT_TEXT.value,
                "template": "The result is {result}.",
            },
        ),
        PlanNode(
            node_id="node_final",
            node_type=NodeType.FINAL,
            name="Final",
            dependencies=["node_format"],
            input_mapping={"final_output": "fmt_out"},
        ),
    ]
    plan = ExecutionPlan(
        plan_id=plan_id,
        task_id=task_id,
        run_id=run_id,
        objective="Calculate 25 * 4 and format",
        nodes=nodes,
    )

    ctx = ExecutionContext(
        task_id=task_id,
        run_id=run_id,
        user_id=uuid.uuid4(),
        plan_id=plan_id,
    )

    response = await executor.execute_graph(plan=plan, context=ctx, session=db_session)

    assert response.status == PlanStatus.COMPLETED
    assert response.final_output == "The result is 100."
    assert "node_calc" in response.completed_nodes
    assert "node_format" in response.completed_nodes
    assert "node_final" in response.completed_nodes


@pytest.mark.asyncio
async def test_graph_executor_branching_and_join(db_session: AsyncSession) -> None:
    executor = GraphExecutor(tool_service=ToolService())
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    await _seed_task_and_plan(db_session, task_id, run_id, plan_id)

    # Node A: 10 + 5 = 15
    # Node B: 20 * 2 = 40
    # Node C (Transform): merge -> format
    # Node D: FINAL
    nodes = [
        PlanNode(
            node_id="calc_a",
            node_type=NodeType.TOOL,
            name="Calc A",
            configuration={"tool_name": "calculator", "arguments": {"expression": "10 + 5"}},
            output_key="out_a",
        ),
        PlanNode(
            node_id="calc_b",
            node_type=NodeType.TOOL,
            name="Calc B",
            configuration={"tool_name": "calculator", "arguments": {"expression": "20 * 2"}},
            output_key="out_b",
        ),
        PlanNode(
            node_id="format_c",
            node_type=NodeType.TRANSFORM,
            name="Format C",
            dependencies=["calc_a", "calc_b"],
            input_mapping={"a": "out_a", "b": "out_b"},
            output_key="out_c",
            configuration={
                "operation": TransformOperation.FORMAT_TEXT.value,
                "template": "A={a}, B={b}",
            },
        ),
        PlanNode(
            node_id="final_d",
            node_type=NodeType.FINAL,
            name="Final D",
            dependencies=["format_c"],
            input_mapping={"final_output": "out_c"},
        ),
    ]

    plan = ExecutionPlan(
        plan_id=plan_id,
        task_id=task_id,
        run_id=run_id,
        objective="Branch and join",
        nodes=nodes,
    )
    ctx = ExecutionContext(
        task_id=task_id,
        run_id=run_id,
        user_id=uuid.uuid4(),
        plan_id=plan_id,
    )

    response = await executor.execute_graph(plan=plan, context=ctx, session=db_session)
    assert response.status == PlanStatus.COMPLETED
    assert response.final_output == "A=15, B=40"


@pytest.mark.asyncio
async def test_graph_executor_failure_and_skip_cascade(db_session: AsyncSession) -> None:
    executor = GraphExecutor(tool_service=ToolService())
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    await _seed_task_and_plan(db_session, task_id, run_id, plan_id)

    # Node A fails (division by zero / invalid)
    # Node B depends on A
    # Node C is FINAL depends on B
    nodes = [
        PlanNode(
            node_id="bad_calc",
            node_type=NodeType.TOOL,
            name="Bad Calc",
            configuration={"tool_name": "calculator", "arguments": {"expression": "1 / 0"}},
            retry_policy=RetryPolicy(max_attempts=1),
        ),
        PlanNode(
            node_id="dependent_b",
            node_type=NodeType.TRANSFORM,
            name="Dependent B",
            dependencies=["bad_calc"],
            configuration={"operation": "format_text"},
        ),
        PlanNode(
            node_id="final_c",
            node_type=NodeType.FINAL,
            name="Final C",
            dependencies=["dependent_b"],
        ),
    ]

    plan = ExecutionPlan(
        plan_id=plan_id,
        task_id=task_id,
        run_id=run_id,
        objective="Failure cascade",
        nodes=nodes,
    )
    ctx = ExecutionContext(
        task_id=task_id,
        run_id=run_id,
        user_id=uuid.uuid4(),
        plan_id=plan_id,
    )

    response = await executor.execute_graph(plan=plan, context=ctx, session=db_session)
    assert response.status == PlanStatus.FAILED
    assert "bad_calc" in response.failed_nodes
    assert "dependent_b" in response.skipped_nodes
    assert "final_c" in response.skipped_nodes
