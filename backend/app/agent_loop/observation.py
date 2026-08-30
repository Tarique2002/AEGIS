"""Observation collection, sanitization, and prompt defense builder for the agent loop."""

import json
from typing import Any

from app.agent_loop.budget import AgentBudget
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentObservation
from app.evaluation.schemas import EvaluationResult, ReflectionRecord
from app.planner.schemas import ExecutionPlan, PlanExecutionResponse


class ObservationBuilder:
    """
    Constructs bounded, sanitized, and prompt-injection-defended observations
    representing the current environment and progress state of the agent loop.
    """

    def __init__(self, policy: AgentLoopPolicy | None = None) -> None:
        self.policy = policy or AgentLoopPolicy()

    def _sanitize_data(self, data: Any) -> Any:
        """Recursively redact sensitive credential keys from data payload."""
        sensitive_keys = {
            "api_key",
            "secret",
            "password",
            "authorization",
            "bearer",
            "access_token",
            "refresh_token",
            "auth_token",
        }
        if isinstance(data, dict):
            sanitized: dict[str, Any] = {}
            for k, v in data.items():
                if any(s in str(k).lower() for s in sensitive_keys):
                    sanitized[k] = "[REDACTED]"
                else:
                    sanitized[k] = self._sanitize_data(v)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        return data

    def build_observation(
        self,
        iteration_number: int,
        task_state: dict[str, Any] | None = None,
        latest_plan: ExecutionPlan | None = None,
        execution_results: PlanExecutionResponse | None = None,
        evaluation_result: EvaluationResult | None = None,
        reflection: ReflectionRecord | None = None,
        relevant_memory: list[dict[str, Any]] | None = None,
        active_errors: list[str] | None = None,
        available_actions: list[str] | None = None,
        budget: AgentBudget | None = None,
        previous_failures: list[dict[str, Any]] | None = None,
    ) -> AgentObservation:
        """
        Assemble and sanitize the observation record.
        """
        clean_task_state = self._sanitize_data(task_state or {})
        clean_memory = self._sanitize_data(relevant_memory or [])
        clean_failures = self._sanitize_data(previous_failures or [])
        remaining_budget = budget.get_remaining_budget() if budget else {}

        actions = available_actions or [
            "plan_next_step",
            "replan_with_reflection",
            "complete_objective",
            "retry_failed_operation",
            "halt_safety_violation",
        ]

        return AgentObservation(
            iteration_number=iteration_number,
            task_state=clean_task_state,
            latest_plan=latest_plan,
            execution_results=execution_results,
            evaluation_result=evaluation_result,
            reflection=reflection,
            relevant_memory=clean_memory,
            active_errors=active_errors or [],
            available_actions=actions,
            remaining_budget=remaining_budget,
            previous_failures=clean_failures,
        )

    def format_prompt_context(self, observation: AgentObservation, objective: str) -> str:
        """
        Format observation into a structured, strict markdown string with distinct
        INSTRUCTION, DATA, and MEMORY delimiters to prevent prompt injection.
        """
        plan_summary = "None"
        if observation.latest_plan:
            nodes_desc = [
                f"- [{n.node_id}] {n.node_type.value}: {n.name} (deps: {n.dependencies})"
                for n in observation.latest_plan.nodes
            ]
            plan_summary = (
                f"Plan ID: {observation.latest_plan.plan_id}\n"
                f"Status: {observation.latest_plan.status.value}\n"
                f"Nodes:\n" + "\n".join(nodes_desc)
            )

        exec_summary = "None"
        if observation.execution_results:
            exec_summary = (
                f"Status: {observation.execution_results.status.value}\n"
                f"Completed: {observation.execution_results.completed_nodes}\n"
                f"Failed: {observation.execution_results.failed_nodes}\n"
                f"Final Output: {observation.execution_results.final_output}"
            )

        eval_summary = "None"
        if observation.evaluation_result:
            eval_summary = (
                f"Overall Score: {observation.evaluation_result.overall_score:.2f} "
                f"(Passed: {observation.evaluation_result.passed})\n"
                f"Strengths: {observation.evaluation_result.strengths}\n"
                f"Weaknesses: {observation.evaluation_result.weaknesses}\n"
                f"Recommendations: {observation.evaluation_result.recommendations}"
            )

        refl_summary = "None"
        if observation.reflection:
            refl_summary = (
                f"Summary: {observation.reflection.summary}\n"
                f"Root Causes: {observation.reflection.root_causes}\n"
                f"What Went Well: {observation.reflection.what_went_well}\n"
                f"What Went Wrong: {observation.reflection.what_went_wrong}\n"
                f"Improvement Suggestions: {observation.reflection.improvement_suggestions}"
            )

        memory_json = json.dumps(observation.relevant_memory, indent=2)
        errors_json = json.dumps(observation.active_errors, indent=2)
        budget_json = json.dumps(observation.remaining_budget, indent=2)

        context_str = f"""### OBJECTIVE (IMMUTABLE INSTRUCTION)
{objective}

### ITERATION
Current Iteration: {observation.iteration_number}

### REMAINING RESOURCE BUDGET
{budget_json}

=== BEGIN UNTRUSTED PREVIOUS EXECUTION DATA ===
[PLAN]
{plan_summary}

[EXECUTION RESULTS]
{exec_summary}

[EVALUATION]
{eval_summary}

[DIAGNOSTIC REFLECTION]
{refl_summary}

[ACTIVE ERRORS]
{errors_json}
=== END UNTRUSTED PREVIOUS EXECUTION DATA ===

=== BEGIN UNTRUSTED RETRIEVED MEMORY DATA ===
{memory_json}
=== END UNTRUSTED RETRIEVED MEMORY DATA ===
"""
        if len(context_str) > self.policy.max_observation_chars:
            context_str = context_str[: self.policy.max_observation_chars] + "\n[...TRUNCATED...]"

        return context_str
