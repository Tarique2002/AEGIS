"""Progress tracking, stagnation detection, repetition guards, and security guardrails."""

import hashlib
import json
from typing import Any

from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentDecision, DecisionType
from app.core.errors import InvalidDecisionError, SafetyStopTriggeredError, StagnationDetectedError
from app.planner.schemas import ExecutionPlan


class ProgressTracker:
    """
    Tracks evaluation score trends, execution signatures, plan hashes, and failure patterns
    across loop iterations to detect progress stagnation, regressions, and infinite loops.
    """

    def __init__(self, policy: AgentLoopPolicy | None = None) -> None:
        self.policy = policy or AgentLoopPolicy()
        self.scores: list[float] = []
        self.plan_hashes: list[str] = []
        self.failure_signatures: dict[str, int] = {}
        self.tool_signatures: dict[str, int] = {}
        self.stagnant_iterations: int = 0

    def compute_plan_hash(self, plan: ExecutionPlan) -> str:
        """Generate a deterministic structural hash of an execution plan."""
        canonical_nodes = [
            {
                "id": n.node_id,
                "type": n.node_type.value,
                "deps": sorted(n.dependencies),
                "config": n.configuration,
            }
            for n in sorted(plan.nodes, key=lambda x: x.node_id)
        ]
        serialized = json.dumps(canonical_nodes, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_failure_signature(self, failure: dict[str, Any]) -> str:
        """Compute unique signature for a failure occurrence."""
        tool = failure.get("tool_name", "")
        node = failure.get("node_type", "")
        err = failure.get("error", "")[:100]
        return f"{tool}::{node}::{err}".strip(":")

    def compute_tool_signature(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Compute signature for a tool invocation."""
        serialized_args = json.dumps(arguments, sort_keys=True)
        return f"{tool_name}::{serialized_args}"

    def record_iteration(
        self,
        eval_score: float | None = None,
        plan: ExecutionPlan | None = None,
        failures: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Record iteration metrics and update stagnation counters."""
        score = eval_score if eval_score is not None else 0.0

        # Check score improvement
        if self.scores:
            prev_best = max(self.scores)
            if score <= prev_best:
                self.stagnant_iterations += 1
            else:
                self.stagnant_iterations = 0
        self.scores.append(score)

        # Track plan repetition
        if plan:
            p_hash = self.compute_plan_hash(plan)
            if p_hash in self.plan_hashes:
                self.stagnant_iterations += 1
            self.plan_hashes.append(p_hash)

        # Track failure repetition
        if failures:
            for f in failures:
                sig = self.compute_failure_signature(f)
                count = self.failure_signatures.get(sig, 0) + 1
                self.failure_signatures[sig] = count
                if count >= 2:
                    self.stagnant_iterations += 1

        # Track tool call repetition
        if tool_calls:
            for t in tool_calls:
                t_name = t.get("tool_name", "")
                t_args = t.get("arguments", {})
                sig = self.compute_tool_signature(t_name, t_args)
                count = self.tool_signatures.get(sig, 0) + 1
                self.tool_signatures[sig] = count

    def check_stagnation(self) -> tuple[bool, str]:
        """Verify whether stagnation thresholds have been breached."""
        # 1. Check repeated identical failure
        for sig, count in self.failure_signatures.items():
            if count >= 3:
                return True, f"Repeated identical failure detected ({count} times): {sig}"

        # 2. Check repeated identical tool calls without progress
        for sig, count in self.tool_signatures.items():
            if count >= 4 and self.stagnant_iterations >= 1:
                return (
                    True,
                    f"Tool loop detected: identical invocation repeated ({count} times): {sig}",
                )

        # 3. Check general score stagnation
        if self.stagnant_iterations >= self.policy.max_stagnant_iterations:
            return (
                True,
                f"No progress detected across {self.stagnant_iterations} consecutive iterations.",
            )

        return False, ""


class AgentGuardrails:
    """
    Security and policy validation layer ensuring that decisions and proposals
    conform to hard bounds, safety invariants, and non-autonomous boundaries.
    """

    def __init__(self, policy: AgentLoopPolicy | None = None) -> None:
        self.policy = policy or AgentLoopPolicy()

    def validate_decision(self, decision: AgentDecision, tracker: ProgressTracker) -> None:
        """Validate proposed decision against safety invariants and stagnation checks."""
        # 1. Stagnation validation
        is_stagnant, reason = tracker.check_stagnation()
        if is_stagnant:
            if decision.decision_type not in (
                DecisionType.FAIL,
                DecisionType.SAFETY_STOP,
                DecisionType.COMPLETE,
            ):
                raise StagnationDetectedError(reason)

        # 2. Decision validity
        if not decision.rationale or not decision.rationale.strip():
            raise InvalidDecisionError("Decision rationale cannot be empty.")

        # 3. Safety stop enforcement
        if decision.decision_type == DecisionType.SAFETY_STOP:
            raise SafetyStopTriggeredError(f"Safety guardrail triggered stop: {decision.rationale}")
