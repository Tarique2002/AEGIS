"""Deterministic and LLM-assisted task planners for generating ExecutionPlans."""

import re
import uuid
from typing import Any

from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.planner.base import BasePlanner
from app.planner.schemas import (
    ExecutionPlan,
    LLMPlanOutput,
    NodeType,
    PlanNode,
    PlanStatus,
    TransformOperation,
)
from app.planner.validator import PlanValidator
from app.schemas.common import ChatMessage, ChatRole

logger = get_logger("aegis.planner.planner")


class DeterministicPlanner(BasePlanner):
    """
    Decomposes objectives into validated execution graphs using deterministic heuristics
    and template matching.
    """

    async def create_plan(
        self,
        objective: str,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        context: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """
        Deconstruct objective into a structured DAG plan.
        Supports arithmetic calculator pipelines, text transformations, and direct synthesis.
        """
        plan_id = uuid.uuid4()
        nodes: list[PlanNode] = []

        # Check for arithmetic calculation pattern (e.g. "Calculate 25 * 4")
        math_match = re.search(r"(\d+\s*[\+\-\*\/\%]\s*\d+)", objective)

        if math_match:
            expr = math_match.group(1).strip()
            # Node 1: Calculator Tool Node
            nodes.append(
                PlanNode(
                    node_id="node_calc",
                    node_type=NodeType.TOOL,
                    name="Calculate Expression",
                    description=f"Evaluate arithmetic expression '{expr}'",
                    dependencies=[],
                    input_mapping={},
                    output_key="calc_output",
                    configuration={
                        "tool_name": "calculator",
                        "arguments": {"expression": expr},
                    },
                )
            )

            # Node 2: Format Transform Node if requested sentence formatting
            if "format" in objective.lower() or "sentence" in objective.lower():
                nodes.append(
                    PlanNode(
                        node_id="node_format",
                        node_type=NodeType.TRANSFORM,
                        name="Format Sentence",
                        description="Format calculated result as a sentence",
                        dependencies=["node_calc"],
                        input_mapping={"result": "calc_output"},
                        output_key="formatted_output",
                        configuration={
                            "operation": TransformOperation.FORMAT_TEXT.value,
                            "template": "The result is {result}.",
                        },
                    )
                )
                # Node 3: FINAL Node
                nodes.append(
                    PlanNode(
                        node_id="node_final",
                        node_type=NodeType.FINAL,
                        name="Final Synthesis",
                        dependencies=["node_format"],
                        input_mapping={"final_output": "formatted_output"},
                    )
                )
            else:
                # Direct FINAL Node
                nodes.append(
                    PlanNode(
                        node_id="node_final",
                        node_type=NodeType.FINAL,
                        name="Final Synthesis",
                        dependencies=["node_calc"],
                        input_mapping={"final_output": "calc_output"},
                    )
                )
        else:
            # Default single-step transform to final
            nodes.append(
                PlanNode(
                    node_id="node_transform",
                    node_type=NodeType.TRANSFORM,
                    name="Process Objective",
                    dependencies=[],
                    input_mapping={"objective": objective},
                    output_key="processed_objective",
                    configuration={
                        "operation": TransformOperation.FORMAT_TEXT.value,
                        "template": "Processed: {objective}",
                    },
                )
            )
            nodes.append(
                PlanNode(
                    node_id="node_final",
                    node_type=NodeType.FINAL,
                    name="Final Synthesis",
                    dependencies=["node_transform"],
                    input_mapping={"final_output": "processed_objective"},
                )
            )

        return ExecutionPlan(
            plan_id=plan_id,
            task_id=task_id,
            run_id=run_id,
            objective=objective,
            version=1,
            nodes=nodes,
            status=PlanStatus.DRAFT,
            metadata=context or {},
        )


class LLMPlanner(BasePlanner):
    """
    LLM-assisted declarative task planner generating structured DAGs
    subject to strict Pydantic parsing and PlanValidator topological checks.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        validator: PlanValidator | None = None,
        deterministic_fallback: DeterministicPlanner | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.validator = validator or PlanValidator()
        self.fallback_planner = deterministic_fallback or DeterministicPlanner()

    async def create_plan(
        self,
        objective: str,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        context: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """
        Generate a multi-step execution plan using LLM structured generation.
        Falls back to DeterministicPlanner if the LLM output is malformed or invalid.
        """
        prompt = f"""You are the AEGIS Autonomous Task Planner.
Decompose the following user objective into a valid Directed Acyclic Graph (DAG) execution plan.

[OBJECTIVE]
{objective}

[RULES]
1. Allowed node types: TOOL, LLM, TRANSFORM, CONDITION, FINAL.
2. Must have exactly one FINAL node that depends on upstream results.
3. Every dependency must be a valid node_id in the plan.
4. No cycles or self-dependencies.
5. Available tools: "calculator".
6. Transform ops: select_field, merge_values, format_text, extract_value, concatenate.
7. Never generate shell commands, OS scripts, or arbitrary code expressions.
"""
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=(
                    "You are an expert declarative planner for autonomous AI agents. "
                    "Return only structured JSON."
                ),
            ),
            ChatMessage(role=ChatRole.USER, content=prompt),
        ]

        try:
            res = await self.llm_provider.generate_structured(
                messages=messages,
                response_model=LLMPlanOutput,
                temperature=0.0,
            )
            plan = ExecutionPlan(
                plan_id=uuid.uuid4(),
                task_id=task_id,
                run_id=run_id,
                objective=objective,
                version=1,
                nodes=res.data.nodes,
                status=PlanStatus.DRAFT,
                metadata=context or {},
            )
            # Validate plan topology
            self.validator.validate_plan(plan)
            return plan

        except Exception as exc:
            logger.warning(
                f"LLM planning failed validation or provider error; fallback active: {exc}"
            )
            return await self.fallback_planner.create_plan(
                objective=objective,
                task_id=task_id,
                run_id=run_id,
                context=context,
            )
