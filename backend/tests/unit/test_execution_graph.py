"""Unit tests for ExecutionGraph DAG representation and dependency resolution."""

import uuid

from app.planner.graph import ExecutionGraph
from app.planner.schemas import ExecutionPlan, NodeType, PlanNode


def test_graph_ready_nodes_linear() -> None:
    nodes = [
        PlanNode(
            node_id="a",
            node_type=NodeType.TOOL,
            name="A",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="b",
            node_type=NodeType.TRANSFORM,
            name="B",
            dependencies=["a"],
            configuration={"operation": "format_text"},
        ),
        PlanNode(node_id="c", node_type=NodeType.FINAL, name="C", dependencies=["b"]),
    ]
    plan = ExecutionPlan(task_id=uuid.uuid4(), run_id=uuid.uuid4(), objective="linear", nodes=nodes)
    graph = ExecutionGraph(plan)

    # Initially, only node 'a' is ready
    ready = graph.get_ready_nodes(set(), set(), set(), set())
    assert [n.node_id for n in ready] == ["a"]

    # When 'a' completes, 'b' is ready
    ready_after_a = graph.get_ready_nodes({"a"}, set(), set(), set())
    assert [n.node_id for n in ready_after_a] == ["b"]


def test_graph_ready_nodes_branching_and_join() -> None:
    # A, B independent -> C waits for A and B -> D is FINAL
    nodes = [
        PlanNode(
            node_id="a",
            node_type=NodeType.TOOL,
            name="A",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="b",
            node_type=NodeType.TOOL,
            name="B",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="c",
            node_type=NodeType.TRANSFORM,
            name="C",
            dependencies=["a", "b"],
            configuration={"operation": "merge_values"},
        ),
        PlanNode(node_id="d", node_type=NodeType.FINAL, name="D", dependencies=["c"]),
    ]
    plan = ExecutionPlan(
        task_id=uuid.uuid4(), run_id=uuid.uuid4(), objective="branch_join", nodes=nodes
    )
    graph = ExecutionGraph(plan)

    ready = graph.get_ready_nodes(set(), set(), set(), set())
    assert {n.node_id for n in ready} == {"a", "b"}

    # Complete 'a' only -> 'c' still not ready because 'b' not completed
    ready_after_a = graph.get_ready_nodes({"a"}, set(), set(), set())
    assert {n.node_id for n in ready_after_a} == {"b"}

    # Complete 'a' and 'b' -> 'c' ready
    ready_after_both = graph.get_ready_nodes({"a", "b"}, set(), set(), set())
    assert [n.node_id for n in ready_after_both] == ["c"]


def test_graph_downstream_dependents_cascade() -> None:
    # a -> b -> c -> d
    # e independent -> d
    nodes = [
        PlanNode(
            node_id="a",
            node_type=NodeType.TOOL,
            name="A",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(
            node_id="b",
            node_type=NodeType.TRANSFORM,
            name="B",
            dependencies=["a"],
            configuration={"operation": "format_text"},
        ),
        PlanNode(
            node_id="c",
            node_type=NodeType.TRANSFORM,
            name="C",
            dependencies=["b"],
            configuration={"operation": "format_text"},
        ),
        PlanNode(
            node_id="e",
            node_type=NodeType.TOOL,
            name="E",
            configuration={"tool_name": "calculator"},
        ),
        PlanNode(node_id="d", node_type=NodeType.FINAL, name="D", dependencies=["c", "e"]),
    ]
    plan = ExecutionPlan(
        task_id=uuid.uuid4(), run_id=uuid.uuid4(), objective="cascade", nodes=nodes
    )
    graph = ExecutionGraph(plan)

    downstream_a = graph.get_downstream_dependents("a")
    assert downstream_a == {"b", "c", "d"}
    assert "e" not in downstream_a
