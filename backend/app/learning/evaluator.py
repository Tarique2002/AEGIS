"""Deterministic outcome evaluator for execution trajectories."""

import uuid

from app.learning.schemas import ExecutionTrajectory, OutcomeEvaluationResult


class OutcomeEvaluator:
    """
    Deterministic evaluation layer for agent execution trajectories.
    Derives quantitative quality, tool effectiveness, step efficiency,
    and confidence scores from observable execution facts.
    """

    def evaluate(self, trajectory: ExecutionTrajectory) -> OutcomeEvaluationResult:
        """Evaluate a trajectory deterministically."""
        # 1. Success indicator
        is_success = bool(trajectory.is_success)
        failures_count = len(trajectory.failures)
        retries_count = trajectory.retries_count

        # 2. Tool effectiveness
        tool_calls = trajectory.tool_calls_metadata
        if not tool_calls:
            tool_effectiveness = 1.0 if is_success else 0.5
        else:
            successful_calls = 0
            for call in tool_calls:
                call_error = call.get("error")
                call_status = call.get("status", "success")
                if not call_error and call_status in ("success", "completed"):
                    successful_calls += 1
            tool_effectiveness = round(successful_calls / max(1, len(tool_calls)), 4)

        # 3. Step efficiency & Unnecessary steps
        # Detect redundant tool invocations (same tool and arguments)
        seen_calls: set[str] = set()
        unnecessary_steps = 0
        for call in tool_calls:
            call_sig = f"{call.get('tool_name')}:{str(call.get('arguments', {}))}"
            if call_sig in seen_calls:
                unnecessary_steps += 1
            else:
                seen_calls.add(call_sig)

        # Unnecessary steps also incremented for any step explicitly marked redundant or failed
        for step in trajectory.planning_steps:
            if step.get("status") in ("failed", "skipped", "cancelled"):
                unnecessary_steps += 1

        total_steps = max(1, len(trajectory.planning_steps) + len(tool_calls))
        raw_efficiency = 1.0 - ((retries_count * 0.15) + (unnecessary_steps / total_steps * 0.4))
        execution_efficiency = round(min(1.0, max(0.05, raw_efficiency)), 4)

        # 4. Policy violations
        policy_violations = 0
        for p in trajectory.policy_decisions:
            if p.get("decision") in (
                "deny",
                "denied",
                "block",
                "blocked",
                "violation",
            ) or not p.get("allowed", True):
                policy_violations += 1

        # 5. Task completion quality
        eval_sum = trajectory.evaluation_summary or {}
        explicit_score = eval_sum.get("overall_score")
        if explicit_score is not None and isinstance(explicit_score, int | float):
            task_completion_quality = round(float(explicit_score), 4)
        elif is_success:
            task_completion_quality = round(
                max(0.2, 1.0 - (failures_count * 0.1) - (policy_violations * 0.3)), 4
            )
        else:
            task_completion_quality = round(max(0.0, 0.4 - (failures_count * 0.1)), 4)

        # 6. Failure reasons
        failure_reasons: list[str] = []
        for fail in trajectory.failures:
            reason = fail.get("error") or fail.get("reason") or str(fail)
            if reason and reason not in failure_reasons:
                failure_reasons.append(str(reason))

        if policy_violations > 0 and "Policy violation detected" not in failure_reasons:
            failure_reasons.append(f"{policy_violations} policy violation(s) detected.")

        # 7. Deterministic composite confidence
        base_confidence = (
            (task_completion_quality * 0.40)
            + (tool_effectiveness * 0.35)
            + (execution_efficiency * 0.25)
        )
        if policy_violations > 0:
            base_confidence -= policy_violations * 0.3
        if not is_success:
            base_confidence *= 0.5

        confidence = round(min(1.0, max(0.0, base_confidence)), 4)

        return OutcomeEvaluationResult(
            evaluation_id=uuid.uuid4(),
            trajectory_id=trajectory.trajectory_id,
            success=is_success and policy_violations == 0,
            task_completion_quality=task_completion_quality,
            tool_effectiveness=tool_effectiveness,
            execution_efficiency=execution_efficiency,
            unnecessary_steps=unnecessary_steps,
            retry_frequency=retries_count,
            failure_reasons=failure_reasons,
            policy_violations=policy_violations,
            confidence=confidence,
        )
