"""AgentController orchestrating multi-iteration execution, termination, and checkpoints."""

import asyncio
import time
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.budget import AgentBudget
from app.agent_loop.errors import (
    BudgetExceededError,
    SafetyStopTriggeredError,
    StagnationDetectedError,
)
from app.agent_loop.guardrails import ProgressTracker
from app.agent_loop.iteration import AgentIterationRunner
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import (
    AgentIterationRecord,
    AgentLoopState,
    AgentLoopStatus,
    ApprovalRequest,
    ApprovalResult,
    AutonomyLevel,
    DecisionType,
)
from app.core.logging import get_logger
from app.observability.events import EventEmitter
from app.schemas.common import utc_now
from app.schemas.event import ExecutionEventType

logger = get_logger("aegis.agent_loop.controller")


class ApprovalProvider(Protocol):
    """Interface for human-in-the-loop approval governance."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Request approval for a governed action."""
        ...


class DefaultApprovalProvider:
    """Default mock approval provider granting approvals automatically for bounded executions."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        return ApprovalResult(
            request_id=request.request_id,
            approved=True,
            reviewer="auto_governance",
            comments="Auto-approved by default bounded policy.",
        )


class AgentController:
    """
    Main orchestrator for controlled autonomous agent loops.
    Executes bounded iterations, enforces hard stop conditions, and manages lifecycle transitions.
    """

    def __init__(
        self,
        iteration_runner: AgentIterationRunner,
        policy: AgentLoopPolicy | None = None,
        event_emitter: EventEmitter | None = None,
        approval_provider: ApprovalProvider | None = None,
    ) -> None:
        self.iteration_runner = iteration_runner
        self.policy = policy or AgentLoopPolicy()
        self.event_emitter = event_emitter or EventEmitter()
        self.approval_provider = approval_provider or DefaultApprovalProvider()

    async def run_loop(
        self,
        loop_state: AgentLoopState,
        autonomy_level: AutonomyLevel = AutonomyLevel.BOUNDED,
        cancellation_token: asyncio.Event | None = None,
        session: AsyncSession | None = None,
    ) -> AgentLoopState:
        """
        Execute the autonomous control loop until completion, budget exhaustion, or safety halt.
        """
        start_time = time.time()
        budget = AgentBudget(policy=self.policy, state=loop_state.budget)
        tracker = ProgressTracker(policy=self.policy)

        loop_state.status = AgentLoopStatus.EXECUTING
        loop_state.updated_at = utc_now()

        await self.event_emitter.emit(
            task_id=loop_state.task_id,
            run_id=loop_state.run_id,
            event_type=ExecutionEventType.AGENT_LOOP_STARTED,
            payload={
                "loop_id": str(loop_state.loop_id),
                "objective": loop_state.objective,
                "max_iterations": self.policy.max_iterations,
                "autonomy_level": autonomy_level.value,
            },
            session=session,
        )

        try:
            while loop_state.iteration_number < self.policy.max_iterations:
                # 1. Check Cancellation
                if cancellation_token and cancellation_token.is_set():
                    loop_state.status = AgentLoopStatus.CANCELLED
                    break

                # 2. Supervised approval check
                if autonomy_level == AutonomyLevel.SUPERVISED:
                    approval_req = ApprovalRequest(
                        loop_id=loop_state.loop_id,
                        action_type="execute_iteration",
                        payload={"iteration": loop_state.iteration_number + 1},
                        rationale="Supervised governance approval required before iteration.",
                    )
                    approval_res = await self.approval_provider.request_approval(approval_req)
                    if not approval_res.approved:
                        loop_state.status = AgentLoopStatus.SAFETY_STOPPED
                        loop_state.errors.append(
                            "Execution halted: human reviewer rejected approval."
                        )
                        break

                # 3. Execute atomic iteration
                iteration_record: AgentIterationRecord = (
                    await self.iteration_runner.execute_iteration(
                        loop_state=loop_state,
                        budget=budget,
                        tracker=tracker,
                        start_time=start_time,
                        cancellation_token=cancellation_token,
                        session=session,
                    )
                )

                # 4. Update Loop State
                loop_state.iteration_number = iteration_record.iteration_number
                loop_state.completed_iterations.append(iteration_record)
                if iteration_record.observation:
                    loop_state.observations.append(iteration_record.observation)
                if iteration_record.decision:
                    loop_state.decisions.append(iteration_record.decision)
                loop_state.updated_at = utc_now()

                # 5. Evaluate Termination Decision
                decision = iteration_record.decision
                if decision:
                    if decision.decision_type == DecisionType.COMPLETE:
                        loop_state.status = AgentLoopStatus.COMPLETED
                        break
                    elif decision.decision_type == DecisionType.SAFETY_STOP:
                        loop_state.status = AgentLoopStatus.SAFETY_STOPPED
                        break
                    elif decision.decision_type == DecisionType.FAIL:
                        loop_state.status = AgentLoopStatus.FAILED
                        break

            # Reached max iterations without completion
            if (
                loop_state.iteration_number >= self.policy.max_iterations
                and loop_state.status not in (AgentLoopStatus.COMPLETED, AgentLoopStatus.CANCELLED)
            ):
                loop_state.status = AgentLoopStatus.BUDGET_EXCEEDED
                loop_state.errors.append(
                    f"Maximum iterations ({self.policy.max_iterations}) reached."
                )

        except BudgetExceededError as exc:
            loop_state.status = AgentLoopStatus.BUDGET_EXCEEDED
            loop_state.errors.append(str(exc))
            await self.event_emitter.emit(
                task_id=loop_state.task_id,
                run_id=loop_state.run_id,
                event_type=ExecutionEventType.AGENT_LOOP_BUDGET_EXCEEDED,
                payload={"error": str(exc)},
                session=session,
            )

        except StagnationDetectedError as exc:
            loop_state.status = AgentLoopStatus.FAILED
            loop_state.errors.append(str(exc))
            await self.event_emitter.emit(
                task_id=loop_state.task_id,
                run_id=loop_state.run_id,
                event_type=ExecutionEventType.AGENT_LOOP_STAGNATION_DETECTED,
                payload={"error": str(exc)},
                session=session,
            )

        except SafetyStopTriggeredError as exc:
            loop_state.status = AgentLoopStatus.SAFETY_STOPPED
            loop_state.errors.append(str(exc))
            await self.event_emitter.emit(
                task_id=loop_state.task_id,
                run_id=loop_state.run_id,
                event_type=ExecutionEventType.AGENT_LOOP_SAFETY_STOPPED,
                payload={"error": str(exc)},
                session=session,
            )

        except Exception as exc:
            logger.exception(f"Unexpected error in agent controller: {exc}")
            loop_state.status = AgentLoopStatus.FAILED
            loop_state.errors.append(f"Controller error: {str(exc)}")

        finally:
            loop_state.completed_at = utc_now()
            loop_state.updated_at = utc_now()

            terminal_event = (
                ExecutionEventType.AGENT_LOOP_COMPLETED
                if loop_state.status == AgentLoopStatus.COMPLETED
                else (
                    ExecutionEventType.AGENT_LOOP_CANCELLED
                    if loop_state.status == AgentLoopStatus.CANCELLED
                    else ExecutionEventType.AGENT_LOOP_FAILED
                )
            )
            await self.event_emitter.emit(
                task_id=loop_state.task_id,
                run_id=loop_state.run_id,
                event_type=terminal_event,
                payload={
                    "loop_id": str(loop_state.loop_id),
                    "status": loop_state.status.value,
                    "completed_iterations": len(loop_state.completed_iterations),
                    "final_result": loop_state.final_result,
                },
                session=session,
            )

        return loop_state
