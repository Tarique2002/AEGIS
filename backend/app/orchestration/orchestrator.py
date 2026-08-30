"""MultiAgentOrchestrator lifecycle coordinator for planning, execution, and synthesis."""

import asyncio
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.service import AgentLoopService
from app.core.logging import get_logger
from app.evaluation.schemas import EvaluationRequest
from app.evaluation.service import EvaluationService
from app.memory.schemas import MemoryCandidate, MemoryType
from app.memory.service import MemoryService
from app.orchestration.aggregator import ResultAggregator
from app.orchestration.collector import WorkerResultCollector
from app.orchestration.delegation import DelegationPlanner
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.scheduler import DAGScheduler
from app.orchestration.schemas import (
    DelegatedTask,
    DelegationExecutionMode,
    DelegationPlan,
    OrchestrationBudgetState,
    OrchestrationState,
    OrchestrationStatus,
    WorkerDefinition,
)
from app.orchestration.worker import WorkerRegistry, WorkerRunner
from app.schemas.common import utc_now

logger = get_logger(__name__)


class MultiAgentOrchestrator:
    """Central authority orchestrating planning, dispatch,
    aggregation, and rework."""

    def __init__(
        self,
        agent_loop_service: AgentLoopService,
        evaluation_service: EvaluationService | None = None,
        memory_service: MemoryService | None = None,
        policy: OrchestrationPolicy | None = None,
        registry: WorkerRegistry | None = None,
        safety_gate: Any | None = None,
    ) -> None:
        self.agent_loop_service = agent_loop_service
        self.evaluation_service = evaluation_service
        self.memory_service = memory_service
        self.policy = policy or OrchestrationPolicy()
        self.registry = registry or WorkerRegistry()
        self.safety_gate = safety_gate

        self.planner = DelegationPlanner(policy=self.policy)
        self.worker_runner = WorkerRunner(
            agent_loop_service=self.agent_loop_service,
            registry=self.registry,
            safety_gate=self.safety_gate,
        )
        self.scheduler = DAGScheduler(
            worker_runner=self.worker_runner,
            policy=self.policy,
        )
        self.collector = WorkerResultCollector()
        self.aggregator = ResultAggregator()

    async def execute_orchestration(
        self,
        orchestration_id: uuid.UUID,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        user_id: uuid.UUID,
        objective: str,
        session: AsyncSession,
        custom_workers: list[WorkerDefinition] | None = None,
        execution_mode: DelegationExecutionMode = DelegationExecutionMode.DEPENDENCY_GRAPH,
        max_parallel_workers: int = 3,
        cancellation_token: asyncio.Event | None = None,
        initial_plan: DelegationPlan | None = None,
    ) -> OrchestrationState:
        """Execute full multi-agent orchestration lifecycle."""
        start_time = time.perf_counter()
        state = OrchestrationState(
            orchestration_id=orchestration_id,
            task_id=task_id,
            run_id=run_id,
            user_id=user_id,
            objective=objective,
            status=OrchestrationStatus.PLANNING,
            budget=OrchestrationBudgetState(),
            started_at=utc_now(),
        )

        try:
            # 1. Delegation Planning
            if initial_plan:
                self.planner.validate_plan(initial_plan)
                plan = initial_plan
            else:
                plan = self.planner.create_heuristic_plan(
                    orchestration_id=orchestration_id,
                    objective=objective,
                    execution_mode=execution_mode,
                    max_parallel_workers=max_parallel_workers,
                )
            state.delegation_plan = plan
            state.budget.worker_count = len(plan.tasks)
            state.status = OrchestrationStatus.RUNNING

            # 1b. Safety Gate Evaluation for Orchestration Plan
            if self.safety_gate:
                from app.safety.schemas import SafetyContext

                s_ctx = SafetyContext(
                    user_id=user_id,
                    task_id=task_id,
                    run_id=run_id,
                    orchestration_id=orchestration_id,
                    action="execute_orchestration_plan",
                    arguments_metadata={"objective": objective, "worker_count": len(plan.tasks)},
                )
                decision = await self.safety_gate.evaluate(s_ctx)
                if not decision.allowed:
                    state.status = OrchestrationStatus.FAILED
                    state.errors.append(f"Orchestration Safety Gate Denied: {decision.reason}")
                    return state

            # 2. Memory Pre-Retrieval (if memory service available)
            relevant_memories: dict[str, list[dict[str, Any]]] = {}
            if self.memory_service:
                try:
                    from app.memory.schemas import MemorySearchQuery

                    for task in plan.tasks:
                        # Fetch relevant episodic memories safely
                        mem_records = await self.memory_service.recall(
                            query=MemorySearchQuery(query_text=task.objective, limit=3),
                            trusted_user_id=user_id,
                            session=session,
                        )
                        if mem_records:
                            relevant_memories[task.delegated_task_id] = [
                                {
                                    "id": str(m.record.memory_id),
                                    "content": m.record.content,
                                    "type": m.record.memory_type.value,
                                }
                                for m in mem_records
                            ]
                except Exception as mem_err:
                    logger.warning(f"Memory pre-retrieval failed: {mem_err}")

            # 3. DAG Scheduling & Worker Execution
            state.status = OrchestrationStatus.DISPATCHING
            raw_results = await self.scheduler.execute_plan(
                plan=plan,
                task_id=task_id,
                run_id=run_id,
                trusted_user_id=user_id,
                session=session,
                budget=state.budget,
                cancellation_token=cancellation_token,
                relevant_memories=relevant_memories,
            )

            # 4. Result Collection & Validation
            validated_results = self.collector.collect_and_validate(plan, raw_results)
            state.worker_results = validated_results

            # 5. Result Aggregation & Conflict Detection
            state.status = OrchestrationStatus.AGGREGATING
            aggregated = self.aggregator.aggregate(orchestration_id, validated_results)
            state.aggregated_result = aggregated
            state.status = aggregated.status

            # 6. Synthesis Evaluation (Phase 4 integration)
            if self.evaluation_service and aggregated.final_output is not None:
                state.status = OrchestrationStatus.EVALUATING
                try:
                    eval_req = EvaluationRequest(
                        task_id=task_id,
                        run_id=run_id,
                        objective=objective,
                        actual_result=str(aggregated.final_output),
                        metadata={
                            "summary": aggregated.summary,
                            "worker_contributions": aggregated.worker_contributions,
                        },
                    )
                    eval_res = await self.evaluation_service.evaluate_run(
                        request=eval_req,
                        trusted_user_id=user_id,
                        session=session,
                    )
                    aggregated.evaluation = eval_res
                    state.aggregated_result = aggregated

                    # Bounded Rework check
                    if (
                        eval_res.overall_score < self.policy.completion_score_threshold
                        and state.budget.rework_rounds < self.policy.max_rework_rounds
                        and state.status != OrchestrationStatus.CANCELLED
                    ):
                        state.budget.rework_rounds += 1
                        logger.info(
                            f"Evaluation score {eval_res.overall_score:.2f} below threshold "
                            f"{self.policy.completion_score_threshold}. Initiating rework round "
                            f"{state.budget.rework_rounds}."
                        )
                        # Execute single targeted synthesis rework pass
                        rework_task = DelegatedTask(
                            delegated_task_id=f"task_rework_{state.budget.rework_rounds}",
                            worker_id="worker_synthesis",
                            worker_type=self.registry.get_worker("worker_synthesis").worker_type,
                            title=f"Targeted Synthesis Rework (Round {state.budget.rework_rounds})",
                            objective=(
                                f"Refine final synthesis addressing evaluation feedback: "
                                f"{eval_res.weaknesses}"
                            ),
                            expected_output="Refined final answer.",
                        )
                        rework_res = await self.worker_runner.execute_task(
                            task=rework_task,
                            task_id=task_id,
                            run_id=run_id,
                            trusted_user_id=user_id,
                            session=session,
                            orchestration_policy=self.policy,
                            cumulative_budget=state.budget,
                            dependency_outputs=aggregated.worker_contributions,
                        )
                        if rework_res.status.value == "COMPLETED" and rework_res.result:
                            aggregated.final_output = rework_res.result
                            aggregated.summary += (
                                f" (Rework round {state.budget.rework_rounds} applied)"
                            )

                    if state.status != OrchestrationStatus.CANCELLED:
                        state.status = aggregated.status
                except Exception as eval_err:
                    logger.warning(f"Synthesis evaluation failed: {eval_err}")

            # 7. Post-Orchestration Episodic Memory Ingestion
            if self.memory_service and state.status == OrchestrationStatus.COMPLETED:
                try:
                    await self.memory_service.remember(
                        candidate=MemoryCandidate(
                            memory_type=MemoryType.EPISODIC,
                            content=(
                                f"Orchestration Objective: {objective} -> "
                                f"Outcome: {aggregated.final_output}"
                            ),
                            metadata={"orchestration_id": str(orchestration_id)},
                        ),
                        trusted_user_id=user_id,
                        session=session,
                    )
                except Exception as mem_write_err:
                    logger.warning(f"Memory write failed: {mem_write_err}")

            state.completed_at = utc_now()
            state.budget.elapsed_time_ms = (time.perf_counter() - start_time) * 1000.0
            return state

        except Exception as exc:
            logger.error(f"Orchestration '{orchestration_id}' failed: {exc}", exc_info=True)
            state.status = OrchestrationStatus.FAILED
            state.errors.append(str(exc))
            state.completed_at = utc_now()
            state.budget.elapsed_time_ms = (time.perf_counter() - start_time) * 1000.0
            return state
