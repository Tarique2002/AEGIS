"""
Unified Evaluation & Reflection Service coordinating security, events,
evaluation, and storage.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import EvaluationNotFoundError
from app.core.logging import get_logger
from app.db.models.event import ExecutionEventModel
from app.db.models.run import AgentRun
from app.db.models.task import Task
from app.evaluation.criteria import get_default_criteria
from app.evaluation.evaluator import EvaluationEngine
from app.evaluation.policies import EvaluationPolicy
from app.evaluation.reflection import ReflectionEngine
from app.evaluation.repository import EvaluationRepository
from app.evaluation.schemas import (
    CriterionScore,
    EvaluationCriterion,
    EvaluationRequest,
    EvaluationResult,
    FailureCategory,
    ReflectionRecord,
    ReflectionRequest,
)
from app.llm.base import LLMProvider
from app.memory.schemas import MemoryCandidate, MemoryType
from app.memory.service import MemoryService
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType

logger = get_logger("aegis.evaluation.service")


class EvaluationService:
    """
    Orchestration service for agent execution evaluation and diagnostic reflection.
    Enforces multi-tenant ownership boundaries and monotonic event emission.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        policy: EvaluationPolicy | None = None,
        event_emitter: EventEmitter | None = None,
        repository: EvaluationRepository | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.repository = repository or EvaluationRepository()
        self.event_emitter = event_emitter or EventEmitter()
        self.evaluation_engine = EvaluationEngine(llm_provider=llm_provider, policy=policy)
        self.reflection_engine = ReflectionEngine(llm_provider=llm_provider)
        self.memory_service = memory_service or MemoryService(emitter=self.event_emitter)

    async def _verify_task_ownership(
        self,
        task_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> Task:
        """Verify task exists and belongs to the trusted user context."""
        stmt = select(Task).where(Task.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise EvaluationNotFoundError(f"Task with ID '{task_id}' not found.")

        if task.user_id is not None and task.user_id != trusted_user_id:
            # Mask existence of other users' tasks
            raise EvaluationNotFoundError(f"Task with ID '{task_id}' not found.")

        return task

    async def _gather_execution_context(
        self,
        task: Task,
        run_id: uuid.UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Collect durable execution facts, telemetry, and event trace points for a run."""
        stmt = select(AgentRun).where(AgentRun.id == run_id, AgentRun.task_id == task.id)
        res = await session.execute(stmt)
        run = res.scalar_one_or_none()

        if not run:
            raise EvaluationNotFoundError(f"Run with ID '{run_id}' not found for task '{task.id}'.")

        # Fetch sequence-ordered events
        ev_stmt = (
            select(ExecutionEventModel)
            .where(ExecutionEventModel.run_id == run_id)
            .order_by(ExecutionEventModel.sequence_number.asc())
        )
        ev_res = await session.execute(ev_stmt)
        events = ev_res.scalars().all()

        return {
            "task_id": str(task.id),
            "run_id": str(run.id),
            "objective": task.objective,
            "status": run.status,
            "result": run.result,
            "error": run.error,
            "state_snapshot": run.state_snapshot,
            "latency_ms": run.latency_ms,
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
            "total_tokens": run.total_tokens,
            "events": [
                {
                    "event_type": e.event_type,
                    "sequence_number": e.sequence_number,
                    "payload": e.payload,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in events
            ],
        }

    async def evaluate_run(
        self,
        request: EvaluationRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        criteria: list[EvaluationCriterion] | None = None,
    ) -> EvaluationResult:
        """
        Evaluate a completed agent execution pass.
        Persists evaluation result and emits monotonic execution events.
        """
        task = await self._verify_task_ownership(request.task_id, trusted_user_id, session)
        execution_ctx = await self._gather_execution_context(task, request.run_id, session)

        await self.event_emitter.emit(
            task_id=task.id,
            run_id=request.run_id,
            event_type=ExecutionEventType.EVALUATION_STARTED,
            payload={"evaluator": "composite", "criteria": request.criteria},
            session=session,
        )

        try:
            eval_result = await self.evaluation_engine.evaluate(
                request=request,
                criteria=criteria or get_default_criteria(),
                execution_context=execution_ctx,
            )

            # Persist to database
            await self.repository.create_evaluation(eval_result, session)
            await session.commit()

            await self.event_emitter.emit(
                task_id=task.id,
                run_id=request.run_id,
                event_type=ExecutionEventType.EVALUATION_COMPLETED,
                payload={
                    "evaluation_id": str(eval_result.evaluation_id),
                    "overall_score": eval_result.overall_score,
                    "passed": eval_result.passed,
                    "failure_categories": [f.value for f in eval_result.failure_categories],
                },
                session=session,
            )

            return eval_result

        except Exception as exc:
            await self.event_emitter.emit(
                task_id=task.id,
                run_id=request.run_id,
                event_type=ExecutionEventType.EVALUATION_FAILED,
                payload={"error": str(exc)},
                session=session,
            )
            raise

    async def get_evaluation(
        self,
        evaluation_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> EvaluationResult:
        """Retrieve an evaluation record by ID with strict ownership validation."""
        model = await self.repository.get_evaluation_by_id(evaluation_id, session)
        if not model:
            raise EvaluationNotFoundError(f"Evaluation with ID '{evaluation_id}' not found.")

        # Verify task ownership
        await self._verify_task_ownership(model.task_id, trusted_user_id, session)

        return EvaluationResult(
            evaluation_id=model.id,
            task_id=model.task_id,
            run_id=model.run_id,
            overall_score=model.overall_score,
            passed=model.passed,
            evaluator=model.evaluator,
            criterion_scores=[CriterionScore(**cs) for cs in model.criterion_scores],
            failure_categories=[FailureCategory(fc) for fc in model.failure_categories],
            strengths=model.strengths,
            weaknesses=model.weaknesses,
            recommendations=model.recommendations,
            created_at=model.created_at,
            metadata=model.evaluation_metadata,
        )

    async def get_task_evaluations(
        self,
        task_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[EvaluationResult]:
        """List all evaluations belonging to a specific task."""
        await self._verify_task_ownership(task_id, trusted_user_id, session)
        models = await self.repository.get_evaluations_by_task_id(task_id, session)

        return [
            EvaluationResult(
                evaluation_id=m.id,
                task_id=m.task_id,
                run_id=m.run_id,
                overall_score=m.overall_score,
                passed=m.passed,
                evaluator=m.evaluator,
                criterion_scores=[CriterionScore(**cs) for cs in m.criterion_scores],
                failure_categories=[FailureCategory(fc) for fc in m.failure_categories],
                strengths=m.strengths,
                weaknesses=m.weaknesses,
                recommendations=m.recommendations,
                created_at=m.created_at,
                metadata=m.evaluation_metadata,
            )
            for m in models
        ]

    async def generate_reflection(
        self,
        evaluation_id: uuid.UUID,
        request: ReflectionRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ReflectionRecord:
        """
        Synthesize reflection record for an evaluation and optionally persist to memory.
        """
        eval_result = await self.get_evaluation(evaluation_id, trusted_user_id, session)
        task = await self._verify_task_ownership(eval_result.task_id, trusted_user_id, session)
        execution_ctx = await self._gather_execution_context(task, eval_result.run_id, session)

        await self.event_emitter.emit(
            task_id=task.id,
            run_id=eval_result.run_id,
            event_type=ExecutionEventType.REFLECTION_STARTED,
            payload={"evaluation_id": str(evaluation_id)},
            session=session,
        )

        try:
            reflection = await self.reflection_engine.reflect(
                evaluation=eval_result,
                request=request,
                execution_context=execution_ctx,
            )

            # Persist reflection model
            await self.repository.create_reflection(reflection, session)

            # Optional Memory Subsystem integration
            if request.persist_to_memory:
                recs_str = "; ".join(reflection.improvement_suggestions)
                candidate_content = (
                    f"Reflection Summary: {reflection.summary}\nRecommendations: {recs_str}"
                )
                candidate = MemoryCandidate(
                    content=candidate_content,
                    memory_type=MemoryType.EPISODIC,
                    importance=0.6 if eval_result.passed else 0.8,
                    task_id=eval_result.task_id,
                    run_id=eval_result.run_id,
                    metadata={
                        "evaluation_id": str(eval_result.evaluation_id),
                        "passed": eval_result.passed,
                        "overall_score": eval_result.overall_score,
                        "root_causes": reflection.root_causes,
                    },
                )
                try:
                    await self.memory_service.remember(
                        candidate=candidate,
                        trusted_user_id=trusted_user_id,
                        session=session,
                    )
                except Exception as mem_err:
                    logger.warning(f"Optional reflection memory ingestion failed: {mem_err}")

            await session.commit()

            await self.event_emitter.emit(
                task_id=task.id,
                run_id=eval_result.run_id,
                event_type=ExecutionEventType.REFLECTION_COMPLETED,
                payload={
                    "reflection_id": str(reflection.reflection_id),
                    "confidence": reflection.confidence,
                    "root_causes": reflection.root_causes,
                },
                session=session,
            )

            return reflection

        except Exception as exc:
            await self.event_emitter.emit(
                task_id=task.id,
                run_id=eval_result.run_id,
                event_type=ExecutionEventType.REFLECTION_FAILED,
                payload={"error": str(exc)},
                session=session,
            )
            raise

    async def get_reflection_by_evaluation_id(
        self,
        evaluation_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ReflectionRecord:
        """Retrieve reflection associated with an evaluation ID."""
        # Validate evaluation and task ownership
        eval_result = await self.get_evaluation(evaluation_id, trusted_user_id, session)

        model = await self.repository.get_reflection_by_evaluation_id(
            eval_result.evaluation_id, session
        )
        if not model:
            raise EvaluationNotFoundError(
                f"Reflection for evaluation ID '{evaluation_id}' not found."
            )

        return ReflectionRecord(
            reflection_id=model.id,
            task_id=model.task_id,
            run_id=model.run_id,
            evaluation_id=model.evaluation_id,
            summary=model.summary,
            what_went_well=model.what_went_well,
            what_went_wrong=model.what_went_wrong,
            root_causes=model.root_causes,
            improvement_suggestions=model.improvement_suggestions,
            confidence=model.confidence,
            created_at=model.created_at,
            metadata=model.reflection_metadata,
        )
