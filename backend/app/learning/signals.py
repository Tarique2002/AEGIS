"""Learning signal extraction engine converting trajectories to distilled feedback signals."""

import uuid

from app.learning.schemas import (
    ExecutionTrajectory,
    LearningSignal,
    LearningSignalType,
    OutcomeEvaluationResult,
)


class LearningSignalGenerator:
    """
    Synthesizes atomic, structured learning signals from execution trajectories
    and outcome evaluation results.
    """

    def generate_signals(
        self,
        trajectory: ExecutionTrajectory,
        evaluation: OutcomeEvaluationResult,
        domain: str = "general",
    ) -> list[LearningSignal]:
        """Extract all relevant learning signals from a trajectory and evaluation."""
        signals: list[LearningSignal] = []

        # 1. Tool Sequence Signals
        tool_names = [
            c.get("tool_name") or c.get("tool", "")
            for c in trajectory.tool_calls_metadata
            if c.get("tool_name") or c.get("tool")
        ]
        if not tool_names and trajectory.selected_tools:
            tool_names = list(trajectory.selected_tools)

        if tool_names:
            if evaluation.success and evaluation.tool_effectiveness >= 0.8:
                signals.append(
                    LearningSignal(
                        signal_id=uuid.uuid4(),
                        trajectory_id=trajectory.trajectory_id,
                        user_id=trajectory.user_id,
                        signal_type=LearningSignalType.SUCCESSFUL_TOOL_SEQUENCE,
                        domain=domain,
                        context={"goal": trajectory.goal, "duration_ms": trajectory.duration_ms},
                        payload={
                            "sequence": tool_names,
                            "effectiveness": evaluation.tool_effectiveness,
                            "tool_calls_count": len(tool_names),
                        },
                        confidence=round(evaluation.confidence * evaluation.tool_effectiveness, 4),
                        discourages_strategy=False,
                    )
                )

            # Failed tool calls
            for call in trajectory.tool_calls_metadata:
                if call.get("error") or call.get("status") == "failed":
                    signals.append(
                        LearningSignal(
                            signal_id=uuid.uuid4(),
                            trajectory_id=trajectory.trajectory_id,
                            user_id=trajectory.user_id,
                            signal_type=LearningSignalType.FAILED_TOOL_SEQUENCE,
                            domain=domain,
                            context={"goal": trajectory.goal},
                            payload={
                                "failed_tool": call.get("tool_name"),
                                "arguments": call.get("arguments", {}),
                                "error": call.get("error"),
                            },
                            confidence=0.85,
                            discourages_strategy=True,
                        )
                    )

        # 2. Planning Pattern Signals
        if trajectory.planning_steps:
            if evaluation.success and evaluation.execution_efficiency >= 0.75:
                signals.append(
                    LearningSignal(
                        signal_id=uuid.uuid4(),
                        trajectory_id=trajectory.trajectory_id,
                        user_id=trajectory.user_id,
                        signal_type=LearningSignalType.SUCCESSFUL_PLANNING_PATTERN,
                        domain=domain,
                        context={"goal": trajectory.goal},
                        payload={
                            "step_count": len(trajectory.planning_steps),
                            "step_descriptions": [
                                s.get("description", s.get("name", ""))
                                for s in trajectory.planning_steps
                            ],
                            "efficiency": evaluation.execution_efficiency,
                        },
                        confidence=evaluation.confidence,
                        discourages_strategy=False,
                    )
                )
            elif not evaluation.success or evaluation.unnecessary_steps >= 2:
                signals.append(
                    LearningSignal(
                        signal_id=uuid.uuid4(),
                        trajectory_id=trajectory.trajectory_id,
                        user_id=trajectory.user_id,
                        signal_type=LearningSignalType.FAILED_PLANNING_PATTERN,
                        domain=domain,
                        context={"goal": trajectory.goal},
                        payload={
                            "unnecessary_steps": evaluation.unnecessary_steps,
                            "reasons": evaluation.failure_reasons,
                            "retries": evaluation.retry_frequency,
                        },
                        confidence=0.8,
                        discourages_strategy=True,
                    )
                )

        # 3. Delegation Pattern Signals (Multi-Agent)
        if trajectory.worker_involvement:
            successful_workers = [
                w
                for w in trajectory.worker_involvement
                if w.get("status") in ("completed", "success")
            ]
            failed_workers = [
                w
                for w in trajectory.worker_involvement
                if w.get("status") in ("failed", "error", "timeout")
            ]

            if evaluation.success and len(successful_workers) == len(trajectory.worker_involvement):
                signals.append(
                    LearningSignal(
                        signal_id=uuid.uuid4(),
                        trajectory_id=trajectory.trajectory_id,
                        user_id=trajectory.user_id,
                        signal_type=LearningSignalType.SUCCESSFUL_DELEGATION_PATTERN,
                        domain=domain,
                        context={"goal": trajectory.goal},
                        payload={
                            "worker_types": [w.get("worker_type") for w in successful_workers],
                            "delegated_subtasks": [w.get("subtask") for w in successful_workers],
                        },
                        confidence=evaluation.confidence,
                        discourages_strategy=False,
                    )
                )
            elif failed_workers:
                signals.append(
                    LearningSignal(
                        signal_id=uuid.uuid4(),
                        trajectory_id=trajectory.trajectory_id,
                        user_id=trajectory.user_id,
                        signal_type=LearningSignalType.FAILED_DELEGATION_PATTERN,
                        domain=domain,
                        context={"goal": trajectory.goal},
                        payload={
                            "failed_workers": [
                                {
                                    "worker_type": w.get("worker_type"),
                                    "subtask": w.get("subtask"),
                                    "error": w.get("error"),
                                }
                                for w in failed_workers
                            ]
                        },
                        confidence=0.85,
                        discourages_strategy=True,
                    )
                )

        # 4. Recovery Strategy Signals
        if trajectory.retries_count > 0 and evaluation.success:
            signals.append(
                LearningSignal(
                    signal_id=uuid.uuid4(),
                    trajectory_id=trajectory.trajectory_id,
                    user_id=trajectory.user_id,
                    signal_type=LearningSignalType.SUCCESSFUL_RECOVERY_STRATEGY,
                    domain=domain,
                    context={"goal": trajectory.goal},
                    payload={
                        "retries_count": trajectory.retries_count,
                        "initial_failures": [f.get("error") for f in trajectory.failures],
                        "recovered_outcome": str(trajectory.final_outcome)[:200],
                    },
                    confidence=round(evaluation.confidence * 0.9, 4),
                    discourages_strategy=False,
                )
            )

        # 5. Recurring Failure Mode Signals
        if not evaluation.success and evaluation.failure_reasons:
            signals.append(
                LearningSignal(
                    signal_id=uuid.uuid4(),
                    trajectory_id=trajectory.trajectory_id,
                    user_id=trajectory.user_id,
                    signal_type=LearningSignalType.RECURRING_FAILURE_MODE,
                    domain=domain,
                    context={"goal": trajectory.goal},
                    payload={
                        "failure_reasons": evaluation.failure_reasons,
                        "policy_violations": evaluation.policy_violations,
                    },
                    confidence=0.9,
                    discourages_strategy=True,
                )
            )

        return signals
