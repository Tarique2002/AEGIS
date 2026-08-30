"""Graph Executor and Node Handlers orchestrating bounded DAG execution."""

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NodeExecutionError
from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.observability.events import EventEmitter
from app.planner.base import BaseNodeHandler
from app.planner.checkpoint import CheckpointManager
from app.planner.graph import ExecutionGraph
from app.planner.policies import PlannerPolicy
from app.planner.retry import RetryHandler
from app.planner.schemas import (
    ConditionOperator,
    ExecutionContext,
    ExecutionPlan,
    NodeStatus,
    NodeType,
    PlanExecutionResponse,
    PlanNode,
    PlanStatus,
    TransformOperation,
)
from app.schemas.common import ChatMessage, ChatRole
from app.schemas.event import ExecutionEventType
from app.tools.schemas import ToolInvocation
from app.tools.service import ToolService

logger = get_logger("aegis.planner.executor")


def resolve_value_from_context(source_key: str, context: ExecutionContext) -> Any:
    """
    Resolve a variable or node output reference from ExecutionContext.
    Supports dot-notation nested path resolution (e.g. 'node_calc.result').
    """
    if not source_key:
        return None

    parts = source_key.split(".")
    root_key = parts[0]

    val = context.node_outputs.get(root_key, context.variables.get(root_key, source_key))

    for part in parts[1:]:
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            break

    return val


class ToolNodeHandler(BaseNodeHandler):
    """Executes a registered tool securely through ToolService / ToolPolicy."""

    def __init__(self, tool_service: ToolService) -> None:
        self.tool_service = tool_service

    async def execute(self, node: PlanNode, context: ExecutionContext) -> Any:
        tool_name = node.configuration.get("tool_name")
        if not tool_name:
            raise NodeExecutionError(
                f"Missing 'tool_name' in configuration for node '{node.node_id}'."
            )

        # Resolve arguments from input mapping
        arguments: dict[str, Any] = {}
        for param, source_key in node.input_mapping.items():
            resolved = resolve_value_from_context(source_key, context)
            if isinstance(resolved, dict) and "result" in resolved and len(resolved) <= 2:
                arguments[param] = resolved["result"]
            else:
                arguments[param] = resolved

        # Merge additional static arguments from configuration
        static_args = node.configuration.get("arguments", {})
        if isinstance(static_args, dict):
            for k, v in static_args.items():
                if k not in arguments:
                    arguments[k] = v

        invocation = ToolInvocation(
            tool_name=tool_name,
            arguments=arguments,
            task_id=context.task_id,
            run_id=context.run_id,
        )

        observation = await self.tool_service.execute_tool(invocation)
        if not observation.success or observation.error:
            raise NodeExecutionError(
                f"Tool '{tool_name}' failed in node '{node.node_id}': {observation.error}"
            )

        return observation.output


class LLMNodeHandler(BaseNodeHandler):
    """Executes a structured or unstructured LLM inference pass."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def execute(self, node: PlanNode, context: ExecutionContext) -> Any:
        template = node.configuration.get("prompt_template", "{input}")
        inputs: dict[str, Any] = {}
        for param, source_key in node.input_mapping.items():
            resolved = resolve_value_from_context(source_key, context)
            if isinstance(resolved, dict) and "result" in resolved and len(resolved) <= 2:
                inputs[param] = resolved["result"]
            else:
                inputs[param] = resolved

        try:
            rendered_prompt = template.format(**inputs)
        except Exception:
            rendered_prompt = f"{template} (Inputs: {inputs})"

        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="You are an autonomous execution component in AEGIS.",
            ),
            ChatMessage(role=ChatRole.USER, content=rendered_prompt),
        ]

        response = await self.llm_provider.generate(
            messages=messages,
            temperature=float(node.configuration.get("temperature", 0.0)),
        )
        return response.content


class TransformNodeHandler(BaseNodeHandler):
    """Executes safe, allowlisted functional transforms with zero eval/exec code execution."""

    async def execute(self, node: PlanNode, context: ExecutionContext) -> Any:
        operation = node.configuration.get("operation")
        inputs: dict[str, Any] = {}
        for param, source_key in node.input_mapping.items():
            resolved = resolve_value_from_context(source_key, context)
            inputs[param] = resolved

        if operation == TransformOperation.SELECT_FIELD.value:
            field = node.configuration.get("field")
            source = inputs.get("source") or inputs.get("input")
            if isinstance(source, dict) and field:
                return source.get(field)
            return source

        elif operation == TransformOperation.MERGE_VALUES.value:
            merged: dict[str, Any] = {}
            for k, v in inputs.items():
                if isinstance(v, dict) and "result" in v and len(v) <= 2:
                    merged[k] = v["result"]
                else:
                    merged[k] = v
            return merged

        elif operation == TransformOperation.FORMAT_TEXT.value:
            template = node.configuration.get("template", "{result}")
            flat_inputs: dict[str, Any] = {}
            for k, v in inputs.items():
                if isinstance(v, dict) and "result" in v and len(v) <= 2:
                    flat_inputs[k] = v["result"]
                else:
                    flat_inputs[k] = v
            try:
                return template.format(**flat_inputs)
            except Exception:
                res = template
                for k, v in flat_inputs.items():
                    res = res.replace(f"{{{k}}}", str(v))
                return res

        elif operation == TransformOperation.EXTRACT_VALUE.value:
            key = node.configuration.get("key")
            source = inputs.get("source") or inputs.get("input")
            if isinstance(source, dict) and key:
                return source.get(key)
            return source

        elif operation == TransformOperation.CONCATENATE.value:
            delimiter = node.configuration.get("delimiter", " ")
            items = inputs.get("items") or list(inputs.values())
            if isinstance(items, list):
                return delimiter.join(str(i) for i in items)
            return str(items)

        raise NodeExecutionError(
            f"Unsupported transform operation '{operation}' in node '{node.node_id}'."
        )


class ConditionNodeHandler(BaseNodeHandler):
    """Evaluates bounded comparisons for conditional branching."""

    async def execute(self, node: PlanNode, context: ExecutionContext) -> Any:
        operator = node.configuration.get("operator")
        left_source = node.input_mapping.get("left", "")
        left_val = resolve_value_from_context(left_source, context)
        if isinstance(left_val, dict) and "result" in left_val and len(left_val) <= 2:
            left_val = left_val["result"]
        right_val = node.configuration.get("right_value")

        matched = False
        if operator == ConditionOperator.EQUALS.value:
            matched = str(left_val) == str(right_val)
        elif operator == ConditionOperator.NOT_EQUALS.value:
            matched = str(left_val) != str(right_val)
        elif operator == ConditionOperator.CONTAINS.value:
            matched = str(right_val) in str(left_val)
        elif operator == ConditionOperator.GREATER_THAN.value:
            try:
                matched = float(left_val or 0.0) > float(right_val or 0.0)
            except (ValueError, TypeError):
                matched = False
        elif operator == ConditionOperator.LESS_THAN.value:
            try:
                matched = float(left_val or 0.0) < float(right_val or 0.0)
            except (ValueError, TypeError):
                matched = False
        elif operator == ConditionOperator.EXISTS.value:
            matched = left_val is not None
        elif operator == ConditionOperator.IS_EMPTY.value:
            matched = not left_val

        return {"matched": matched, "value": left_val}


class FinalNodeHandler(BaseNodeHandler):
    """Gathers and consolidates final execution outcome."""

    async def execute(self, node: PlanNode, context: ExecutionContext) -> Any:
        source_key = node.input_mapping.get("final_output") or node.input_mapping.get("result")
        if source_key:
            val = resolve_value_from_context(source_key, context)
            if isinstance(val, dict) and "result" in val and len(val) <= 2:
                return val["result"]
            return val
        if context.node_outputs:
            last_key = list(context.node_outputs.keys())[-1]
            val = context.node_outputs[last_key]
            if isinstance(val, dict) and "result" in val and len(val) <= 2:
                return val["result"]
            return val
        return "Completed"


class GraphExecutor:
    """
    Executes a validated ExecutionPlan graph with bounded parallel concurrency,
    monotonic event emission, failure isolation, and checkpoint management.
    """

    def __init__(
        self,
        tool_service: ToolService | None = None,
        llm_provider: LLMProvider | None = None,
        policy: PlannerPolicy | None = None,
        event_emitter: EventEmitter | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:
        self.policy = policy or PlannerPolicy()
        self.event_emitter = event_emitter or EventEmitter()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()

        self.tool_service = tool_service or ToolService()
        self.node_handlers: dict[NodeType, BaseNodeHandler] = {
            NodeType.TOOL: ToolNodeHandler(self.tool_service),
            NodeType.TRANSFORM: TransformNodeHandler(),
            NodeType.CONDITION: ConditionNodeHandler(),
            NodeType.FINAL: FinalNodeHandler(),
        }
        if llm_provider:
            self.node_handlers[NodeType.LLM] = LLMNodeHandler(llm_provider)

    async def execute_graph(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        session: AsyncSession,
        cancellation_token: asyncio.Event | None = None,
    ) -> PlanExecutionResponse:
        """
        Execute execution plan DAG to completion or terminal failure.
        """
        start_time = time.time()
        graph = ExecutionGraph(plan)
        semaphore = asyncio.Semaphore(self.policy.max_parallel_nodes)

        completed_nodes: set[str] = set()
        running_nodes: set[str] = set()
        failed_nodes: set[str] = set()
        skipped_nodes: set[str] = set()

        # Seed already completed nodes from checkpoint if resuming
        for n_id, st in context.node_statuses.items():
            if st == NodeStatus.COMPLETED:
                completed_nodes.add(n_id)
            elif st == NodeStatus.SKIPPED:
                skipped_nodes.add(n_id)

        await self.event_emitter.emit(
            task_id=context.task_id,
            run_id=context.run_id,
            event_type=ExecutionEventType.GRAPH_EXECUTION_STARTED,
            payload={"plan_id": str(plan.plan_id), "node_count": len(graph.nodes)},
            session=session,
        )

        final_output: Any = None
        plan_error: str | None = None

        while True:
            # Check cancellation token
            if cancellation_token and cancellation_token.is_set():
                plan_error = "Execution was cancelled."
                break

            ready_nodes = graph.get_ready_nodes(
                completed_nodes=completed_nodes,
                running_nodes=running_nodes,
                failed_nodes=failed_nodes,
                skipped_nodes=skipped_nodes,
            )

            # Terminal condition: no ready nodes and no running nodes
            if not ready_nodes and not running_nodes:
                break

            # Execute batch of ready nodes with bounded concurrency
            async def _run_node_task(node: PlanNode) -> tuple[PlanNode, Any, Exception | None]:
                async with semaphore:
                    running_nodes.add(node.node_id)
                    context.node_statuses[node.node_id] = NodeStatus.RUNNING

                    await self.event_emitter.emit(
                        task_id=context.task_id,
                        run_id=context.run_id,
                        event_type=ExecutionEventType.NODE_STARTED,
                        payload={"node_id": node.node_id, "node_type": node.node_type.value},
                        session=session,
                    )

                    handler = self.node_handlers.get(node.node_type)
                    if not handler:
                        return (
                            node,
                            None,
                            NodeExecutionError(f"No handler for node type '{node.node_type}'."),
                        )

                    attempt = 1
                    last_exc: Exception | None = None

                    while attempt <= node.retry_policy.max_attempts:
                        try:
                            output = await asyncio.wait_for(
                                handler.execute(node, context),
                                timeout=node.timeout_seconds,
                            )
                            return node, output, None
                        except TimeoutError:
                            last_exc = NodeExecutionError(
                                f"Node '{node.node_id}' timed out after {node.timeout_seconds}s."
                            )
                        except Exception as exc:
                            last_exc = exc

                        if RetryHandler.is_retryable(last_exc, attempt, node.retry_policy):
                            backoff = RetryHandler.calculate_backoff_seconds(
                                attempt, node.retry_policy
                            )
                            await self.event_emitter.emit(
                                task_id=context.task_id,
                                run_id=context.run_id,
                                event_type=ExecutionEventType.NODE_RETRIED,
                                payload={
                                    "node_id": node.node_id,
                                    "attempt": attempt,
                                    "backoff_seconds": backoff,
                                },
                                session=session,
                            )
                            if backoff > 0:
                                await asyncio.sleep(backoff)
                            attempt += 1
                        else:
                            break

                    return (
                        node,
                        None,
                        (
                            last_exc
                            or NodeExecutionError(f"Node '{node.node_id}' execution failed.")
                        ),
                    )

            # Schedule ready nodes
            tasks = [asyncio.create_task(_run_node_task(n)) for n in ready_nodes]
            if tasks:
                results = await asyncio.gather(*tasks)

                for node, output, error in results:
                    running_nodes.discard(node.node_id)

                    if error is None:
                        completed_nodes.add(node.node_id)
                        context.node_statuses[node.node_id] = NodeStatus.COMPLETED

                        out_key = node.output_key or node.node_id
                        context.node_outputs[out_key] = output
                        if node.node_type == NodeType.FINAL:
                            final_output = output

                        await self.event_emitter.emit(
                            task_id=context.task_id,
                            run_id=context.run_id,
                            event_type=ExecutionEventType.NODE_COMPLETED,
                            payload={"node_id": node.node_id, "output_key": out_key},
                            session=session,
                        )

                        # Save checkpoint
                        await self.checkpoint_manager.save_checkpoint(
                            context=context,
                            completed_nodes=list(completed_nodes),
                            node_states=context.node_statuses,
                            node_outputs=context.node_outputs,
                            session=session,
                        )
                    else:
                        failed_nodes.add(node.node_id)
                        context.node_statuses[node.node_id] = NodeStatus.FAILED
                        context.errors[node.node_id] = str(error)

                        await self.event_emitter.emit(
                            task_id=context.task_id,
                            run_id=context.run_id,
                            event_type=ExecutionEventType.NODE_FAILED,
                            payload={"node_id": node.node_id, "error": str(error)},
                            session=session,
                        )

                        # Cascade downstream skipped nodes
                        downstream = graph.get_downstream_dependents(node.node_id)
                        for down_id in downstream:
                            if down_id not in completed_nodes and down_id not in failed_nodes:
                                skipped_nodes.add(down_id)
                                context.node_statuses[down_id] = NodeStatus.SKIPPED
                                await self.event_emitter.emit(
                                    task_id=context.task_id,
                                    run_id=context.run_id,
                                    event_type=ExecutionEventType.NODE_SKIPPED,
                                    payload={
                                        "node_id": down_id,
                                        "reason": f"Dependency '{node.node_id}' failed.",
                                    },
                                    session=session,
                                )

                        final_node = graph.get_final_node()
                        if final_node and (
                            final_node.node_id in downstream or final_node.node_id == node.node_id
                        ):
                            plan_error = f"Critical path failure at node '{node.node_id}': {error}"

        duration_ms = round((time.time() - start_time) * 1000, 2)
        final_node = graph.get_final_node()
        final_completed = final_node is not None and final_node.node_id in completed_nodes

        plan_status = (
            PlanStatus.COMPLETED if final_completed and not plan_error else PlanStatus.FAILED
        )
        if cancellation_token and cancellation_token.is_set():
            plan_status = PlanStatus.CANCELLED

        await self.event_emitter.emit(
            task_id=context.task_id,
            run_id=context.run_id,
            event_type=(
                ExecutionEventType.GRAPH_EXECUTION_COMPLETED
                if plan_status == PlanStatus.COMPLETED
                else ExecutionEventType.GRAPH_EXECUTION_FAILED
            ),
            payload={
                "plan_id": str(plan.plan_id),
                "status": plan_status.value,
                "completed_count": len(completed_nodes),
                "failed_count": len(failed_nodes),
                "duration_ms": duration_ms,
            },
            session=session,
        )

        return PlanExecutionResponse(
            plan_id=plan.plan_id,
            task_id=context.task_id,
            run_id=context.run_id,
            status=plan_status,
            final_output=final_output,
            completed_nodes=list(completed_nodes),
            failed_nodes=list(failed_nodes),
            skipped_nodes=list(skipped_nodes),
            node_outputs=context.node_outputs,
            duration_ms=duration_ms,
            error=plan_error,
        )
