"""Worker agent definitions, capability boundaries, prompt defense, and execution runner."""

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_loop.schemas import (
    AgentLoopCreateRequest,
    AgentLoopResponse,
    AutonomyLevel,
)
from app.agent_loop.service import AgentLoopService
from app.core.logging import get_logger
from app.memory.schemas import MemoryType
from app.orchestration.policies import OrchestrationPolicy
from app.orchestration.schemas import (
    DelegatedTask,
    DelegatedTaskStatus,
    OrchestrationBudgetState,
    WorkerDefinition,
    WorkerResult,
    WorkerType,
)
from app.schemas.common import utc_now

logger = get_logger(__name__)


class WorkerRegistry:
    """Registry managing standard worker definitions and their explicit capability constraints."""

    _DEFAULT_WORKERS: dict[WorkerType, WorkerDefinition] = {
        WorkerType.GENERAL: WorkerDefinition(
            worker_id="worker_general",
            worker_type=WorkerType.GENERAL,
            name="General Assistant Worker",
            description="Versatile worker for general multi-step reasoning and coordination.",
            capabilities=["reasoning", "general_tasks"],
            allowed_tools=["calculator"],
            allowed_memory_types=[
                MemoryType.WORKING,
                MemoryType.EPISODIC,
                MemoryType.SEMANTIC,
            ],
            max_iterations=5,
            max_tool_calls=10,
            max_llm_calls=8,
            timeout_seconds=120.0,
        ),
        WorkerType.RESEARCH: WorkerDefinition(
            worker_id="worker_research",
            worker_type=WorkerType.RESEARCH,
            name="Research & Knowledge Worker",
            description=(
                "Specialized worker for factual discovery, memory search, and background retrieval."
            ),
            capabilities=["retrieval", "search", "fact_finding"],
            allowed_tools=["search_memory", "get_memory"],
            allowed_memory_types=[MemoryType.EPISODIC, MemoryType.SEMANTIC],
            max_iterations=4,
            max_tool_calls=8,
            max_llm_calls=6,
            timeout_seconds=120.0,
        ),
        WorkerType.ANALYSIS: WorkerDefinition(
            worker_id="worker_analysis",
            worker_type=WorkerType.ANALYSIS,
            name="Quantitative Analysis Worker",
            description=(
                "Specialized worker for mathematical computation, "
                "statistical analysis, and verification."
            ),
            capabilities=["calculation", "data_analysis", "statistics"],
            allowed_tools=["calculator"],
            allowed_memory_types=[MemoryType.WORKING, MemoryType.EPISODIC],
            max_iterations=4,
            max_tool_calls=10,
            max_llm_calls=6,
            timeout_seconds=120.0,
        ),
        WorkerType.CODING: WorkerDefinition(
            worker_id="worker_coding",
            worker_type=WorkerType.CODING,
            name="Logic & Code Analysis Worker",
            description=(
                "Specialized worker for algorithmic reasoning and "
                "deterministic logic transformation."
            ),
            capabilities=["logic", "algorithmic_reasoning"],
            allowed_tools=["calculator"],
            allowed_memory_types=[MemoryType.WORKING],
            max_iterations=5,
            max_tool_calls=10,
            max_llm_calls=8,
            timeout_seconds=120.0,
        ),
        WorkerType.DATA: WorkerDefinition(
            worker_id="worker_data",
            worker_type=WorkerType.DATA,
            name="Data Extraction & Structuring Worker",
            description=(
                "Specialized worker for data structuring, transformation, " "and schema extraction."
            ),
            capabilities=["data_extraction", "schema_validation"],
            allowed_tools=["calculator"],
            allowed_memory_types=[MemoryType.WORKING, MemoryType.SEMANTIC],
            max_iterations=4,
            max_tool_calls=6,
            max_llm_calls=6,
            timeout_seconds=120.0,
        ),
        WorkerType.SYNTHESIS: WorkerDefinition(
            worker_id="worker_synthesis",
            worker_type=WorkerType.SYNTHESIS,
            name="Synthesis & Aggregation Worker",
            description=(
                "Specialized worker for combining intermediate evidence into "
                "cohesive final answers."
            ),
            capabilities=["summarization", "synthesis", "integration"],
            allowed_tools=[],  # Strictly no external tool access
            allowed_memory_types=[MemoryType.WORKING, MemoryType.EPISODIC],
            max_iterations=3,
            max_tool_calls=0,
            max_llm_calls=4,
            timeout_seconds=90.0,
        ),
    }

    def __init__(self, custom_workers: list[WorkerDefinition] | None = None) -> None:
        self._workers: dict[str, WorkerDefinition] = {
            w.worker_id: w for w in self._DEFAULT_WORKERS.values()
        }
        if custom_workers:
            for w in custom_workers:
                self._workers[w.worker_id] = w

    def get_worker(self, worker_id: str) -> WorkerDefinition:
        """Fetch worker definition by ID, falling back to default role matching."""
        if worker_id in self._workers:
            return self._workers[worker_id]
        # Match by worker type name if ID is e.g. "RESEARCH"
        for w in self._workers.values():
            if (
                w.worker_type.value.lower() == worker_id.lower()
                or w.worker_id.lower() == worker_id.lower()
            ):
                return w
        return self._DEFAULT_WORKERS[WorkerType.GENERAL]

    def get_by_type(self, worker_type: WorkerType) -> WorkerDefinition:
        """Fetch canonical default worker definition for a role."""
        return self._DEFAULT_WORKERS.get(worker_type, self._DEFAULT_WORKERS[WorkerType.GENERAL])


class WorkerContext:
    """Builder that formats safe worker prompts with untrusted data isolation."""

    @staticmethod
    def build_worker_objective(
        task: DelegatedTask,
        dependency_outputs: dict[str, Any] | None = None,
        relevant_memory: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Construct structured objective prompt isolating untrusted inputs and dependency data.
        """
        sections = [
            f"### WORKER OBJECTIVE (TASK: {task.title})",
            task.objective,
            "",
            "### EXPECTED OUTPUT",
            task.expected_output,
        ]

        if task.input_context:
            sections.extend(
                [
                    "",
                    "=== BEGIN APPROVED INPUT CONTEXT (UNTRUSTED DATA) ===",
                    str(task.input_context),
                    "=== END APPROVED INPUT CONTEXT ===",
                ]
            )

        if dependency_outputs:
            sections.extend(
                [
                    "",
                    "=== BEGIN DEPENDENCY DATA FROM PREVIOUS WORKERS (UNTRUSTED DATA) ===",
                ]
            )
            for dep_id, out in dependency_outputs.items():
                sections.append(f"--- Output from Dependency [{dep_id}] ---")
                sections.append(str(out))
            sections.append("=== END DEPENDENCY DATA ===")

        if relevant_memory:
            sections.extend(
                [
                    "",
                    "=== BEGIN RETRIEVED EPISODIC/SEMANTIC MEMORY (UNTRUSTED DATA) ===",
                    str(relevant_memory),
                    "=== END RETRIEVED MEMORY ===",
                ]
            )

        return "\n".join(sections)


class WorkerRunner:
    """Executes a delegated task via Phase 6 AgentLoop runtime with hierarchical budget bounds."""

    def __init__(
        self,
        agent_loop_service: AgentLoopService,
        registry: WorkerRegistry | None = None,
        safety_gate: Any | None = None,
    ) -> None:
        self.agent_loop_service = agent_loop_service
        self.registry = registry or WorkerRegistry()
        self.safety_gate = safety_gate

    async def execute_task(
        self,
        task: DelegatedTask,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        orchestration_policy: OrchestrationPolicy,
        cumulative_budget: OrchestrationBudgetState,
        dependency_outputs: dict[str, Any] | None = None,
        relevant_memory: list[dict[str, Any]] | None = None,
    ) -> WorkerResult:
        """Execute a delegated worker task through the bounded Phase 6 AgentLoop runtime."""
        start_time = time.perf_counter()
        started_at = utc_now()
        worker_def = self.registry.get_worker(task.worker_id)

        # 1. Compute hierarchical budget limits (min of worker def & orchestration remaining)
        remaining_iterations = max(
            1, orchestration_policy.max_total_iterations - cumulative_budget.total_iterations
        )
        remaining_tool_calls = max(
            0, orchestration_policy.max_total_tool_calls - cumulative_budget.total_tool_calls
        )
        remaining_llm_calls = max(
            1, orchestration_policy.max_total_llm_calls - cumulative_budget.total_llm_calls
        )

        effective_max_iterations = min(worker_def.max_iterations, remaining_iterations)
        effective_max_tool_calls = min(worker_def.max_tool_calls, remaining_tool_calls)
        effective_max_llm_calls = min(worker_def.max_llm_calls, remaining_llm_calls)

        # 1b. Safety Gate Evaluation (Phase 8)
        if self.safety_gate:
            from app.safety.schemas import SafetyContext

            s_ctx = SafetyContext(
                user_id=trusted_user_id,
                task_id=task_id,
                run_id=run_id,
                worker_id=task.worker_id,
                action=f"dispatch_worker_{task.worker_id}",
                requested_capabilities=worker_def.capabilities,
            )
            decision = await self.safety_gate.evaluate(s_ctx)
            if not decision.allowed:
                return WorkerResult(
                    delegated_task_id=task.delegated_task_id,
                    worker_id=task.worker_id,
                    worker_type=worker_def.worker_type,
                    status=DelegatedTaskStatus.FAILED,
                    result=None,
                    error=f"Worker Safety Gate Denied: {decision.reason}",
                    started_at=started_at,
                    completed_at=utc_now(),
                    duration_ms=(time.perf_counter() - start_time) * 1000.0,
                )

        # 2. Format isolated worker objective
        worker_objective = WorkerContext.build_worker_objective(
            task=task,
            dependency_outputs=dependency_outputs,
            relevant_memory=relevant_memory,
        )

        loop_request = AgentLoopCreateRequest(
            task_id=task_id,
            run_id=run_id,
            objective=worker_objective,
            autonomy_level=AutonomyLevel.BOUNDED,
            idempotency_key=None,
            metadata={
                "delegated_task_id": task.delegated_task_id,
                "worker_id": task.worker_id,
                "worker_type": task.worker_type.value,
                "max_iterations": effective_max_iterations,
                "max_tool_calls": effective_max_tool_calls,
                "max_llm_calls": effective_max_llm_calls,
            },
        )

        try:
            logger.info(
                f"Dispatching worker '{task.worker_id}' ({task.worker_type.value}) "
                f"for task '{task.delegated_task_id}'"
            )
            loop_response: AgentLoopResponse = await self.agent_loop_service.create_and_start_loop(
                request=loop_request,
                trusted_user_id=trusted_user_id,
                session=session,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Map loop status to worker status
            status_val = (
                DelegatedTaskStatus.COMPLETED
                if loop_response.status.value == "COMPLETED"
                else DelegatedTaskStatus.FAILED
            )

            raw_res = loop_response.final_result
            return WorkerResult(
                worker_id=task.worker_id,
                delegated_task_id=task.delegated_task_id,
                worker_type=task.worker_type,
                status=status_val,
                result=raw_res,
                confidence=0.9 if status_val == DelegatedTaskStatus.COMPLETED else 0.3,
                evidence=[f"Loop completed in {loop_response.iteration_number} iterations"],
                execution_summary=f"Worker finished with status {status_val.value}",
                started_at=started_at,
                completed_at=utc_now(),
                duration_ms=duration_ms,
                metadata={
                    "loop_id": str(loop_response.loop_id),
                    "iterations": loop_response.iteration_number,
                    "budget": loop_response.budget.model_dump(),
                },
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                f"Worker '{task.worker_id}' failed execution: {exc}",
                exc_info=True,
            )
            return WorkerResult(
                worker_id=task.worker_id,
                delegated_task_id=task.delegated_task_id,
                worker_type=task.worker_type,
                status=DelegatedTaskStatus.FAILED,
                result=None,
                confidence=0.0,
                evidence=[],
                execution_summary=f"Worker failed with exception: {exc}",
                started_at=started_at,
                completed_at=utc_now(),
                duration_ms=duration_ms,
                error=str(exc),
                metadata={},
            )
