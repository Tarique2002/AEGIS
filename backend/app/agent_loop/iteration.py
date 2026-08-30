"""Atomic iteration runner coordinating Observe, Plan, Execute, Evaluate, Reflect, Decide."""

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.budget import AgentBudget
from app.agent_loop.decision import DecisionEngine
from app.agent_loop.guardrails import AgentGuardrails, ProgressTracker
from app.agent_loop.observation import ObservationBuilder
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import (
    AgentDecision,
    AgentIterationRecord,
    AgentLoopState,
    AgentLoopStatus,
    DecisionType,
)
from app.core.logging import get_logger
from app.evaluation.schemas import (
    EvaluationRequest,
    EvaluationResult,
    ReflectionRecord,
    ReflectionRequest,
)
from app.evaluation.service import EvaluationService
from app.memory.schemas import MemorySearchQuery, MemoryType
from app.memory.service import MemoryService
from app.observability.events import EventEmitter
from app.planner.schemas import (
    ExecutionPlan,
    PlanCreateRequest,
    PlanExecuteRequest,
    PlanExecutionResponse,
)
from app.planner.service import PlannerService
from app.schemas.common import utc_now
from app.schemas.event import ExecutionEventType

logger = get_logger("aegis.agent_loop.iteration")


class AgentIterationRunner:
    """
    Executes a single atomic loop iteration across Observe, Plan, Execute,
    Evaluate, Reflect, and Decide phases while checking cancellation and budgets.
    """

    def __init__(
        self,
        planner_service: PlannerService,
        evaluation_service: EvaluationService,
        memory_service: MemoryService | None = None,
        policy: AgentLoopPolicy | None = None,
        event_emitter: EventEmitter | None = None,
        observation_builder: ObservationBuilder | None = None,
        decision_engine: DecisionEngine | None = None,
        guardrails: AgentGuardrails | None = None,
    ) -> None:
        self.planner_service = planner_service
        self.evaluation_service = evaluation_service
        self.memory_service = memory_service
        self.policy = policy or AgentLoopPolicy()
        self.event_emitter = event_emitter or EventEmitter()
        self.observation_builder = observation_builder or ObservationBuilder(policy=self.policy)
        self.decision_engine = decision_engine or DecisionEngine(policy=self.policy)
        self.guardrails = guardrails or AgentGuardrails(policy=self.policy)

    async def execute_iteration(
        self,
        loop_state: AgentLoopState,
        budget: AgentBudget,
        tracker: ProgressTracker,
        start_time: float,
        cancellation_token: asyncio.Event | None = None,
        session: AsyncSession | None = None,
    ) -> AgentIterationRecord:
        """
        Execute one complete iteration pass.
        """
        iteration_number = loop_state.iteration_number + 1
        iteration_start = utc_now()
        budget.consume_iteration(1)
        budget.check_time_limit(start_time)

        await self.event_emitter.emit(
            task_id=loop_state.task_id,
            run_id=loop_state.run_id,
            event_type=ExecutionEventType.AGENT_ITERATION_STARTED,
            payload={"iteration_number": iteration_number, "loop_id": str(loop_state.loop_id)},
            session=session,
        )

        active_plan: ExecutionPlan | None = None
        exec_response: PlanExecutionResponse | None = None
        eval_result: EvaluationResult | None = None
        reflection: ReflectionRecord | None = None
        relevant_memory: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        iteration_error: str | None = None

        # 1. OBSERVE & RECALL
        try:
            if (
                self.memory_service
                and budget.state.memory_reads < self.policy.max_memory_retrievals
            ):
                budget.consume_memory_read(1)
                search_query = MemorySearchQuery(
                    query_text=loop_state.objective,
                    limit=3,
                    memory_types=[MemoryType.EPISODIC, MemoryType.PROCEDURAL],
                )
                memory_hits = await self.memory_service.recall(
                    query=search_query,
                    trusted_user_id=loop_state.user_id,
                    task_id=loop_state.task_id,
                    run_id=loop_state.run_id,
                    session=session,
                )
                relevant_memory = [
                    {
                        "content": h.record.content,
                        "score": h.score,
                        "type": h.record.memory_type.value,
                    }
                    for h in memory_hits
                ]
        except Exception as exc:
            logger.warning(f"Memory recall skipped: {exc}")

        obs = self.observation_builder.build_observation(
            iteration_number=iteration_number,
            task_state={"objective": loop_state.objective, "iteration": iteration_number},
            latest_plan=active_plan,
            relevant_memory=relevant_memory,
            active_errors=loop_state.errors,
            budget=budget,
            previous_failures=failures,
        )

        await self.event_emitter.emit(
            task_id=loop_state.task_id,
            run_id=loop_state.run_id,
            event_type=ExecutionEventType.AGENT_OBSERVATION_CREATED,
            payload={
                "iteration_number": iteration_number,
                "observation_id": str(obs.observation_id),
            },
            session=session,
        )

        if cancellation_token and cancellation_token.is_set():
            return AgentIterationRecord(
                loop_id=loop_state.loop_id,
                iteration_number=iteration_number,
                status=AgentLoopStatus.CANCELLED,
                observation=obs,
                started_at=iteration_start,
                completed_at=utc_now(),
                error="Iteration cancelled by user.",
            )

        # 2. PLAN (If new plan or replanning required)
        last_decision = loop_state.decisions[-1] if loop_state.decisions else None
        requires_new_plan = (
            loop_state.current_plan_id is None
            or (last_decision and last_decision.next_plan_required)
            or (last_decision and last_decision.decision_type == DecisionType.REPLAN)
        )

        if session is not None:
            if requires_new_plan:
                budget.consume_plan_execution(1)
                plan_req = PlanCreateRequest(
                    task_id=loop_state.task_id,
                    run_id=loop_state.run_id,
                    objective=loop_state.objective,
                    metadata={
                        "iteration": iteration_number,
                        "previous_errors": loop_state.errors,
                        "reflection": (
                            loop_state.observations[-1].reflection.model_dump()
                            if loop_state.observations and loop_state.observations[-1].reflection
                            else None
                        ),
                    },
                )
                active_plan = await self.planner_service.create_and_validate_plan(
                    request=plan_req,
                    trusted_user_id=loop_state.user_id,
                    session=session,
                )
                loop_state.current_plan_id = active_plan.plan_id
            elif loop_state.current_plan_id:
                active_plan = await self.planner_service.get_plan(
                    plan_id=loop_state.current_plan_id,
                    trusted_user_id=loop_state.user_id,
                    session=session,
                )

        if cancellation_token and cancellation_token.is_set():
            return AgentIterationRecord(
                loop_id=loop_state.loop_id,
                iteration_number=iteration_number,
                status=AgentLoopStatus.CANCELLED,
                observation=obs,
                plan_id=active_plan.plan_id if active_plan else None,
                started_at=iteration_start,
                completed_at=utc_now(),
                error="Iteration cancelled before execution.",
            )

        # 3. EXECUTE GRAPH
        if active_plan and session is not None:
            exec_req = PlanExecuteRequest(variables={"iteration": iteration_number})
            exec_response = await self.planner_service.execute_plan(
                plan_id=active_plan.plan_id,
                request=exec_req,
                trusted_user_id=loop_state.user_id,
                cancellation_token=cancellation_token,
                session=session,
            )
            budget.record_elapsed_time(exec_response.duration_ms)

            # Register tool calls executed
            for node in active_plan.nodes:
                if node.node_type.value == "TOOL" and node.node_id in exec_response.completed_nodes:
                    tool_name = node.configuration.get("tool_name", "")
                    tool_args = node.configuration.get("arguments", {})
                    budget.consume_tool_call(1)
                    tool_calls.append({"tool_name": tool_name, "arguments": tool_args})

            if exec_response.error:
                failures.append({"node_id": "graph", "error": exec_response.error})
                loop_state.errors.append(f"Plan error: {exec_response.error}")

        # 4. EVALUATE
        if session is not None:
            try:
                eval_req = EvaluationRequest(
                    run_id=loop_state.run_id,
                    task_id=loop_state.task_id,
                    metadata={
                        "objective": loop_state.objective,
                        "final_output": exec_response.final_output if exec_response else None,
                        "plan_status": exec_response.status.value if exec_response else "UNKNOWN",
                    },
                )
                eval_result = await self.evaluation_service.evaluate_run(
                    request=eval_req,
                    trusted_user_id=loop_state.user_id,
                    session=session,
                )
            except Exception as exc:
                logger.warning(f"Evaluation failed: {exc}")

        # 5. REFLECT
        if eval_result and (not eval_result.passed or failures) and session is not None:
            try:
                refl_req = ReflectionRequest(evaluation_id=eval_result.evaluation_id)
                reflection = await self.evaluation_service.generate_reflection(
                    evaluation_id=eval_result.evaluation_id,
                    request=refl_req,
                    trusted_user_id=loop_state.user_id,
                    session=session,
                )
            except Exception as exc:
                logger.warning(f"Reflection synthesis failed: {exc}")

        # 6. DECIDE
        eval_score = eval_result.overall_score if eval_result else None
        tracker.record_iteration(
            eval_score=eval_score,
            plan=active_plan,
            failures=failures,
            tool_calls=tool_calls,
        )

        updated_obs = self.observation_builder.build_observation(
            iteration_number=iteration_number,
            task_state={"objective": loop_state.objective, "iteration": iteration_number},
            latest_plan=active_plan,
            execution_results=exec_response,
            evaluation_result=eval_result,
            reflection=reflection,
            relevant_memory=relevant_memory,
            active_errors=loop_state.errors,
            budget=budget,
            previous_failures=failures,
        )

        decision = await self.decision_engine.make_decision(
            observation=updated_obs,
            tracker=tracker,
            budget=budget,
            objective=loop_state.objective,
        )

        # Validate decision with guardrails
        try:
            self.guardrails.validate_decision(decision, tracker)
        except Exception as exc:
            iteration_error = str(exc)
            decision = AgentDecision(
                iteration_number=iteration_number,
                decision_type=DecisionType.FAIL,
                rationale=f"Guardrail violation: {exc}",
                stop_reason=str(exc),
            )

        await self.event_emitter.emit(
            task_id=loop_state.task_id,
            run_id=loop_state.run_id,
            event_type=ExecutionEventType.AGENT_DECISION_CREATED,
            payload={
                "iteration_number": iteration_number,
                "decision_type": decision.decision_type.value,
                "rationale": decision.rationale,
            },
            session=session,
        )

        # Update final result if completed
        if decision.decision_type == DecisionType.COMPLETE and exec_response:
            loop_state.final_result = exec_response.final_output

        await self.event_emitter.emit(
            task_id=loop_state.task_id,
            run_id=loop_state.run_id,
            event_type=ExecutionEventType.AGENT_ITERATION_COMPLETED,
            payload={
                "iteration_number": iteration_number,
                "decision": decision.decision_type.value,
                "duration_ms": round((time.time() - iteration_start.timestamp()) * 1000, 2),
            },
            session=session,
        )

        iter_status = (
            AgentLoopStatus.COMPLETED
            if decision.decision_type == DecisionType.COMPLETE
            else (
                AgentLoopStatus.FAILED
                if decision.decision_type in (DecisionType.FAIL, DecisionType.SAFETY_STOP)
                else AgentLoopStatus.EXECUTING
            )
        )

        return AgentIterationRecord(
            loop_id=loop_state.loop_id,
            iteration_number=iteration_number,
            status=iter_status,
            observation=updated_obs,
            decision=decision,
            plan_id=active_plan.plan_id if active_plan else None,
            evaluation_id=eval_result.evaluation_id if eval_result else None,
            reflection_id=reflection.reflection_id if reflection else None,
            started_at=iteration_start,
            completed_at=utc_now(),
            error=iteration_error,
        )
