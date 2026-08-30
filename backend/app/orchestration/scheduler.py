"""DAG execution scheduler with bounded concurrency and cascade blocking."""

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import (
    DelegatedTask,
    DelegatedTaskStatus,
    DelegationPlan,
    OrchestrationBudgetState,
    WorkerResult,
)
from app.orchestration.worker import WorkerRunner

logger = get_logger(__name__)


class DAGScheduler:
    """Schedules and executes worker tasks adhering to DAG dependencies and bounded concurrency."""

    def __init__(
        self,
        worker_runner: WorkerRunner,
        policy: OrchestrationPolicy | None = None,
    ) -> None:
        self.worker_runner = worker_runner
        self.policy = policy or OrchestrationPolicy()

    async def execute_plan(
        self,
        plan: DelegationPlan,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        budget: OrchestrationBudgetState,
        cancellation_token: asyncio.Event | None = None,
        relevant_memories: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, WorkerResult]:
        """
        Execute all tasks in the delegation plan respecting dependencies and concurrency limits.
        """
        semaphore = asyncio.Semaphore(plan.max_parallel_workers)
        task_map: dict[str, DelegatedTask] = {t.delegated_task_id: t for t in plan.tasks}
        results: dict[str, WorkerResult] = {}
        task_outputs: dict[str, Any] = {}

        # Track unresolved required/optional dependencies
        unresolved_deps: dict[str, set[str]] = {
            t.delegated_task_id: set(t.dependencies) for t in plan.tasks
        }
        blocked_tasks: set[str] = set()
        running_tasks: dict[str, asyncio.Task[Any]] = {}

        session_lock = asyncio.Lock()

        async def run_single_worker(t_id: str) -> None:
            task = task_map[t_id]
            task.status = DelegatedTaskStatus.RUNNING
            budget.active_workers += 1

            # Prepare dependency outputs
            dep_data = {
                dep: task_outputs.get(dep) for dep in task.dependencies if dep in task_outputs
            }
            mem = relevant_memories.get(t_id) if relevant_memories else None

            async with semaphore:
                if cancellation_token and cancellation_token.is_set():
                    task.status = DelegatedTaskStatus.CANCELLED
                    budget.active_workers -= 1
                    return

                try:
                    async with session_lock:
                        res = await asyncio.wait_for(
                            self.worker_runner.execute_task(
                                task=task,
                                task_id=task_id,
                                run_id=run_id,
                                trusted_user_id=trusted_user_id,
                                session=session,
                                orchestration_policy=self.policy,
                                cumulative_budget=budget,
                                dependency_outputs=dep_data,
                                relevant_memory=mem,
                            ),
                            timeout=task.timeout_seconds,
                        )
                except TimeoutError:
                    logger.warning(f"Worker task '{t_id}' timed out after {task.timeout_seconds}s")
                    res = WorkerResult(
                        worker_id=task.worker_id,
                        delegated_task_id=t_id,
                        worker_type=task.worker_type,
                        status=DelegatedTaskStatus.TIMEOUT,
                        confidence=0.0,
                        execution_summary=f"Worker timed out after {task.timeout_seconds}s",
                        error=f"Task exceeded allocated timeout of {task.timeout_seconds}s",
                    )
                except asyncio.CancelledError:
                    task.status = DelegatedTaskStatus.CANCELLED
                    budget.active_workers -= 1
                    raise

            budget.active_workers -= 1
            results[t_id] = res
            task.status = res.status

            if res.status == DelegatedTaskStatus.COMPLETED:
                budget.completed_workers += 1
                task_outputs[t_id] = res.result
            else:
                budget.failed_workers += 1

            # Update cumulative budget metrics from worker metadata if available
            loop_budget = res.metadata.get("budget", {})
            budget.total_iterations += loop_budget.get("total_iterations", 1)
            budget.total_tool_calls += loop_budget.get("total_tool_calls", 0)
            budget.total_llm_calls += loop_budget.get("total_llm_calls", 1)
            budget.elapsed_time_ms += res.duration_ms

        # Main scheduling loop
        while len(results) + len(blocked_tasks) < len(plan.tasks):
            if cancellation_token and cancellation_token.is_set():
                logger.info(f"Cancellation requested for plan '{plan.plan_id}'")
                for _running_id, r_task in running_tasks.items():
                    if not r_task.done():
                        r_task.cancel()
                for remaining_id, remaining_task in task_map.items():
                    if remaining_id not in results and remaining_id not in blocked_tasks:
                        remaining_task.status = DelegatedTaskStatus.CANCELLED
                        results[remaining_id] = WorkerResult(
                            worker_id=remaining_task.worker_id,
                            delegated_task_id=remaining_id,
                            worker_type=remaining_task.worker_type,
                            status=DelegatedTaskStatus.CANCELLED,
                            execution_summary="Task cancelled before execution.",
                        )
                break

            # 1. Identify READY tasks whose dependencies are fulfilled
            ready_to_launch: list[str] = []
            for t_id, task in task_map.items():
                if t_id in results or t_id in blocked_tasks or t_id in running_tasks:
                    continue

                deps = unresolved_deps[t_id]
                # Check if any required dependency failed
                failed_required_dep = any(
                    dep in results
                    and results[dep].status != DelegatedTaskStatus.COMPLETED
                    and not task_map[dep].is_optional
                    for dep in task.dependencies
                )
                if failed_required_dep:
                    logger.warning(f"Blocking task '{t_id}' due to failed required dependency.")
                    task.status = DelegatedTaskStatus.BLOCKED
                    blocked_tasks.add(t_id)
                    results[t_id] = WorkerResult(
                        worker_id=task.worker_id,
                        delegated_task_id=t_id,
                        worker_type=task.worker_type,
                        status=DelegatedTaskStatus.BLOCKED,
                        execution_summary="Task blocked due to failed required dependency.",
                        error="Required dependency failed to complete successfully.",
                    )
                    budget.failed_workers += 1
                    continue

                # Remove completed dependencies
                completed_deps = {
                    dep
                    for dep in deps
                    if dep in results and results[dep].status == DelegatedTaskStatus.COMPLETED
                }
                deps -= completed_deps

                # If optional dependencies failed, also discard them
                optional_failed_deps = {
                    dep
                    for dep in deps
                    if dep in results
                    and results[dep].status != DelegatedTaskStatus.COMPLETED
                    and task_map[dep].is_optional
                }
                deps -= optional_failed_deps

                if not deps:
                    ready_to_launch.append(t_id)

            # 2. Launch ready tasks
            for t_id in ready_to_launch:
                task_map[t_id].status = DelegatedTaskStatus.READY
                running_tasks[t_id] = asyncio.create_task(run_single_worker(t_id))

            if not running_tasks:
                if len(results) + len(blocked_tasks) < len(plan.tasks):
                    # Stagnation safety check
                    logger.error(
                        "Scheduler stagnation: no tasks running and unresolved dependencies remain."
                    )
                break

            # 3. Wait for at least one running task to complete
            done, _ = await asyncio.wait(
                list(running_tasks.values()), return_when=asyncio.FIRST_COMPLETED
            )
            # Clean up completed tasks from active dict
            for t_id, r_task in list(running_tasks.items()):
                if r_task in done:
                    del running_tasks[t_id]

        return results
