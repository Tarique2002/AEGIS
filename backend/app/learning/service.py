"""Self-Learning & Agent Evolution Service.
Coordinates trajectories, evaluations, signals, and procedures.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.learning import (
    LearnedProcedureModel,
    LearningSignalModel,
    ProcedurePromotionAuditModel,
    TrajectoryModel,
)
from app.learning.evaluator import OutcomeEvaluator
from app.learning.promotion import PromotionManager, PromotionPolicy
from app.learning.sanitizer import sanitize_data
from app.learning.schemas import (
    ExecutionTrajectory,
    LearnedProcedure,
    LearningSignal,
    LearningStatsResponse,
    OutcomeEvaluationResult,
    ProcedurePromotionDecision,
    PromotionStatus,
    StrategyRecommendationQuery,
    StrategyRecommendationResponse,
    TrajectoryCreate,
)
from app.learning.strategy import StrategySelector
from app.memory.procedural.store import ProceduralMemoryStore
from app.memory.schemas import ProceduralMemoryRecord
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType

logger = get_logger("aegis.learning.service")


class SelfLearningService:
    """
    Unified Self-Learning & Agent Evolution application service.
    Orchestrates trajectory capture, deterministic outcome evaluation,
    learning signal extraction, safe promotion gating, and strategy recommendation.
    """

    def __init__(
        self,
        evaluator: OutcomeEvaluator | None = None,
        promotion_manager: PromotionManager | None = None,
        strategy_selector: StrategySelector | None = None,
        procedural_store: ProceduralMemoryStore | None = None,
        event_emitter: EventEmitter | None = None,
        promotion_policy: PromotionPolicy | None = None,
    ) -> None:
        self.evaluator = evaluator or OutcomeEvaluator()
        self.promotion_manager = promotion_manager or PromotionManager(policy=promotion_policy)
        self.strategy_selector = strategy_selector or StrategySelector()
        self.procedural_store = procedural_store or ProceduralMemoryStore()
        self.event_emitter = event_emitter or EventEmitter()

    async def capture_trajectory(
        self,
        create_data: TrajectoryCreate,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionTrajectory:
        """Sanitize and persist execution trajectory to PostgreSQL."""
        sanitized_goal = sanitize_data(create_data.goal)
        sanitized_planning = sanitize_data(create_data.planning_steps)
        sanitized_tool_calls = sanitize_data(create_data.tool_calls_metadata)
        sanitized_workers = sanitize_data(create_data.worker_involvement)
        sanitized_decisions = sanitize_data(create_data.intermediate_decisions)
        sanitized_failures = sanitize_data(create_data.failures)
        sanitized_outcome = sanitize_data(create_data.final_outcome)
        sanitized_policies = sanitize_data(create_data.policy_decisions)
        sanitized_eval_summary = sanitize_data(create_data.evaluation_summary)

        trajectory_id = uuid.uuid4()
        model = TrajectoryModel(
            id=trajectory_id,
            user_id=trusted_user_id,
            task_id=create_data.task_id,
            run_id=create_data.run_id,
            goal=sanitized_goal,
            planning_steps=sanitized_planning,
            selected_tools=create_data.selected_tools,
            tool_calls_metadata=sanitized_tool_calls,
            worker_involvement=sanitized_workers,
            intermediate_decisions=sanitized_decisions,
            failures=sanitized_failures,
            retries_count=create_data.retries_count,
            final_outcome=sanitized_outcome
            if isinstance(sanitized_outcome, dict)
            else {"result": sanitized_outcome},
            is_success=create_data.is_success,
            duration_ms=create_data.duration_ms,
            tokens_used=create_data.tokens_used,
            cost_usd=create_data.cost_usd,
            policy_decisions=sanitized_policies,
            evaluation_summary=sanitized_eval_summary,
            trajectory_metadata={},
        )
        session.add(model)
        await session.flush()

        trajectory = ExecutionTrajectory(
            trajectory_id=trajectory_id,
            task_id=create_data.task_id,
            run_id=create_data.run_id,
            user_id=trusted_user_id,
            goal=sanitized_goal,
            planning_steps=sanitized_planning,
            selected_tools=create_data.selected_tools,
            tool_calls_metadata=sanitized_tool_calls,
            worker_involvement=sanitized_workers,
            intermediate_decisions=sanitized_decisions,
            failures=sanitized_failures,
            retries_count=create_data.retries_count,
            final_outcome=sanitized_outcome,
            is_success=create_data.is_success,
            duration_ms=create_data.duration_ms,
            tokens_used=create_data.tokens_used,
            cost_usd=create_data.cost_usd,
            policy_decisions=sanitized_policies,
            evaluation_summary=sanitized_eval_summary,
            created_at=model.created_at,
        )

        await self.event_emitter.emit(
            task_id=create_data.task_id,
            run_id=create_data.run_id,
            event_type=ExecutionEventType.TRAJECTORY_CAPTURED,
            payload={
                "trajectory_id": str(trajectory_id),
                "is_success": trajectory.is_success,
                "tool_count": len(trajectory.selected_tools),
            },
            session=session,
        )
        return trajectory

    async def process_completed_run(
        self,
        create_data: TrajectoryCreate,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        domain: str = "general",
    ) -> tuple[
        ExecutionTrajectory,
        OutcomeEvaluationResult,
        list[LearningSignal],
        ProcedurePromotionDecision | None,
    ]:
        """
        Full autonomous feedback loop:
        Trajectory -> Outcome Evaluation -> Learning Signals
        -> Candidate Proposal -> Promotion Check -> Procedural Memory Update.
        """
        # 1. Capture and sanitize trajectory
        trajectory = await self.capture_trajectory(create_data, trusted_user_id, session)

        # 2. Deterministic Outcome Evaluation
        evaluation = self.evaluator.evaluate(trajectory)
        await self.event_emitter.emit(
            task_id=trajectory.task_id,
            run_id=trajectory.run_id,
            event_type=ExecutionEventType.OUTCOME_EVALUATED,
            payload={
                "evaluation_id": str(evaluation.evaluation_id),
                "success": evaluation.success,
                "task_completion_quality": evaluation.task_completion_quality,
                "confidence": evaluation.confidence,
                "efficiency": evaluation.execution_efficiency,
            },
            session=session,
        )

        # 3. Generate Learning Signals
        from app.learning.signals import LearningSignalGenerator

        sig_gen = LearningSignalGenerator()
        signals = sig_gen.generate_signals(trajectory, evaluation, domain=domain)

        for sig in signals:
            sig_model = LearningSignalModel(
                id=sig.signal_id,
                user_id=trusted_user_id,
                trajectory_id=trajectory.trajectory_id,
                signal_type=sig.signal_type.value,
                domain=sig.domain,
                context=sig.context,
                payload=sig.payload,
                confidence=sig.confidence,
                discourages_strategy=sig.discourages_strategy,
            )
            session.add(sig_model)

            await self.event_emitter.emit(
                task_id=trajectory.task_id,
                run_id=trajectory.run_id,
                event_type=ExecutionEventType.LEARNING_SIGNAL_GENERATED,
                payload={
                    "signal_id": str(sig.signal_id),
                    "signal_type": sig.signal_type.value,
                    "confidence": sig.confidence,
                    "discourages": sig.discourages_strategy,
                },
                session=session,
            )

        # 4. Propose and Evaluate Candidate Procedure
        promotion_decision: ProcedurePromotionDecision | None = None
        if evaluation.success:
            candidate = self.promotion_manager.create_candidate(
                trajectory, evaluation, domain=domain
            )
            await self.event_emitter.emit(
                task_id=trajectory.task_id,
                run_id=trajectory.run_id,
                event_type=ExecutionEventType.PROCEDURE_CANDIDATE_CREATED,
                payload={"candidate_id": str(candidate.candidate_id), "name": candidate.name},
                session=session,
            )

            # Check if there is an existing procedure for this domain & name to upgrade
            existing_proc = await self._find_matching_procedure(
                user_id=trusted_user_id,
                domain=domain,
                name=candidate.name,
                session=session,
            )

            decision, promoted_proc = self.promotion_manager.evaluate_and_promote(
                candidate=candidate,
                evaluation=evaluation,
                actor="autonomous_feedback_loop",
                existing_procedure=existing_proc,
            )
            promotion_decision = decision

            # Record promotion audit
            audit_model = ProcedurePromotionAuditModel(
                id=decision.audit_id,
                user_id=trusted_user_id,
                candidate_id=decision.candidate_id,
                procedure_id=decision.procedure_id,
                promoted=decision.promoted,
                reason=decision.reason,
                actor=decision.actor,
                evaluation_score=decision.evaluation_score,
                confidence=decision.confidence,
                validation_passed=decision.validation_passed,
                version_transition=decision.version_transition,
                audit_metadata={"trajectory_id": str(trajectory.trajectory_id)},
            )
            session.add(audit_model)

            if decision.promoted and promoted_proc:
                # Persist promoted procedure in PostgreSQL
                await self._save_procedure_model(promoted_proc, session)

                # Sync to ProceduralMemoryStore
                proc_record = ProceduralMemoryRecord(
                    procedure_id=promoted_proc.procedure_id,
                    name=promoted_proc.name,
                    description=promoted_proc.description,
                    steps=promoted_proc.ordered_steps,
                    user_id=trusted_user_id,
                    version=promoted_proc.version,
                    importance=promoted_proc.confidence,
                    metadata={
                        "domain": promoted_proc.task_domain,
                        "required_tools": promoted_proc.required_tools,
                        "trigger_conditions": promoted_proc.trigger_conditions,
                    },
                    created_at=promoted_proc.created_at,
                    updated_at=promoted_proc.updated_at,
                )
                await self.procedural_store.register_procedure(proc_record)

                await self.event_emitter.emit(
                    task_id=trajectory.task_id,
                    run_id=trajectory.run_id,
                    event_type=ExecutionEventType.PROCEDURE_PROMOTED,
                    payload={
                        "procedure_id": str(promoted_proc.procedure_id),
                        "version": promoted_proc.version,
                        "confidence": promoted_proc.confidence,
                    },
                    session=session,
                )
            else:
                await self.event_emitter.emit(
                    task_id=trajectory.task_id,
                    run_id=trajectory.run_id,
                    event_type=ExecutionEventType.PROCEDURE_REJECTED,
                    payload={
                        "candidate_id": str(candidate.candidate_id),
                        "reason": decision.reason,
                    },
                    session=session,
                )

        await session.flush()
        return trajectory, evaluation, signals, promotion_decision

    async def recommend_strategies(
        self,
        query: StrategyRecommendationQuery,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> StrategyRecommendationResponse:
        """Retrieve and rank learned procedures matching the objective for trusted user."""
        stmt = select(LearnedProcedureModel).where(
            (LearnedProcedureModel.user_id == trusted_user_id)
            | (LearnedProcedureModel.is_global.is_(True)),
            LearnedProcedureModel.status == PromotionStatus.PROMOTED.value,
        )
        res = await session.execute(stmt)
        models = res.scalars().all()

        procedures = [self._model_to_procedure(m) for m in models]
        recommendations = self.strategy_selector.rank_procedures(
            query=query,
            procedures=procedures,
            user_id=trusted_user_id,
        )

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.STRATEGY_RETRIEVED,
            payload={
                "objective": query.objective[:100],
                "matches_count": len(recommendations),
            },
            session=session,
        )

        return StrategyRecommendationResponse(
            recommendations=recommendations,
            total_matches=len(recommendations),
        )

    async def get_trajectory(
        self,
        trajectory_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionTrajectory | None:
        """Fetch trajectory ensuring tenant isolation."""
        stmt = select(TrajectoryModel).where(
            TrajectoryModel.id == trajectory_id,
            TrajectoryModel.user_id == trusted_user_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._model_to_trajectory(model)

    async def list_trajectories(
        self,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionTrajectory]:
        """List tenant-scoped execution trajectories."""
        stmt = (
            select(TrajectoryModel)
            .where(TrajectoryModel.user_id == trusted_user_id)
            .order_by(TrajectoryModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(stmt)
        return [self._model_to_trajectory(m) for m in res.scalars().all()]

    async def get_procedure(
        self,
        procedure_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> LearnedProcedure | None:
        """Fetch learned procedure with tenant isolation."""
        stmt = select(LearnedProcedureModel).where(
            LearnedProcedureModel.id == procedure_id,
            (LearnedProcedureModel.user_id == trusted_user_id)
            | (LearnedProcedureModel.is_global.is_(True)),
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._model_to_procedure(model)

    async def list_procedures(
        self,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        status: PromotionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LearnedProcedure]:
        """List learned procedures visible to the trusted user."""
        stmt = select(LearnedProcedureModel).where(
            (LearnedProcedureModel.user_id == trusted_user_id)
            | (LearnedProcedureModel.is_global.is_(True))
        )
        if status:
            stmt = stmt.where(LearnedProcedureModel.status == status.value)

        stmt = stmt.order_by(
            LearnedProcedureModel.confidence.desc(), LearnedProcedureModel.updated_at.desc()
        )
        stmt = stmt.limit(limit).offset(offset)
        res = await session.execute(stmt)
        return [self._model_to_procedure(m) for m in res.scalars().all()]

    async def list_signals(
        self,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LearningSignal]:
        """List distilled learning signals for the trusted user."""
        stmt = (
            select(LearningSignalModel)
            .where(LearningSignalModel.user_id == trusted_user_id)
            .order_by(LearningSignalModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(stmt)
        return [
            LearningSignal(
                signal_id=m.id,
                trajectory_id=m.trajectory_id,
                user_id=m.user_id,
                signal_type=m.signal_type,  # type: ignore
                domain=m.domain,
                context=m.context,
                payload=m.payload,
                confidence=m.confidence,
                discourages_strategy=m.discourages_strategy,
                created_at=m.created_at,
            )
            for m in res.scalars().all()
        ]

    async def deprecate_procedure(
        self,
        procedure_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> bool:
        """Deprecate a procedure so it is no longer recommended."""
        stmt = select(LearnedProcedureModel).where(
            LearnedProcedureModel.id == procedure_id,
            LearnedProcedureModel.user_id == trusted_user_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return False

        model.status = PromotionStatus.DEPRECATED.value
        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.PROCEDURE_DEPRECATED,
            payload={"procedure_id": str(procedure_id)},
            session=session,
        )
        return True

    async def get_learning_stats(
        self,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> LearningStatsResponse:
        """Retrieve aggregated learning statistics for the tenant."""
        # Trajectories count
        traj_stmt = select(
            func.count(TrajectoryModel.id).label("total"),
            func.count(TrajectoryModel.id)
            .filter(TrajectoryModel.is_success.is_(True))
            .label("success"),
        ).where(TrajectoryModel.user_id == trusted_user_id)
        traj_res = (await session.execute(traj_stmt)).one()
        total_traj = traj_res.total or 0
        success_traj = traj_res.success or 0

        # Signals count
        sig_stmt = select(func.count(LearningSignalModel.id)).where(
            LearningSignalModel.user_id == trusted_user_id
        )
        total_signals = (await session.execute(sig_stmt)).scalar() or 0

        # Procedures stats
        proc_stmt = select(
            func.count(LearnedProcedureModel.id).label("total"),
            func.count(LearnedProcedureModel.id)
            .filter(LearnedProcedureModel.status == PromotionStatus.PROMOTED.value)
            .label("promoted"),
            func.avg(LearnedProcedureModel.confidence).label("avg_conf"),
        ).where(LearnedProcedureModel.user_id == trusted_user_id)
        proc_res = (await session.execute(proc_stmt)).one()

        return LearningStatsResponse(
            total_trajectories=total_traj,
            successful_trajectories=success_traj,
            failed_trajectories=total_traj - success_traj,
            total_signals=total_signals,
            active_procedures=proc_res.total or 0,
            promoted_procedures=proc_res.promoted or 0,
            average_confidence=round(float(proc_res.avg_conf or 0.0), 4),
        )

    async def _find_matching_procedure(
        self,
        user_id: uuid.UUID,
        domain: str,
        name: str,
        session: AsyncSession,
    ) -> LearnedProcedure | None:
        stmt = select(LearnedProcedureModel).where(
            LearnedProcedureModel.user_id == user_id,
            LearnedProcedureModel.task_domain == domain,
            LearnedProcedureModel.name == name,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        return self._model_to_procedure(model) if model else None

    async def _save_procedure_model(
        self,
        proc: LearnedProcedure,
        session: AsyncSession,
    ) -> None:
        stmt = select(LearnedProcedureModel).where(LearnedProcedureModel.id == proc.procedure_id)
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()

        if model:
            model.task_domain = proc.task_domain
            model.name = proc.name
            model.description = proc.description
            model.trigger_conditions = proc.trigger_conditions
            model.ordered_steps = proc.ordered_steps
            model.required_tools = proc.required_tools
            model.constraints = proc.constraints
            model.success_criteria = proc.success_criteria
            model.confidence = proc.confidence
            model.usage_count = proc.usage_count
            model.success_count = proc.success_count
            model.failure_count = proc.failure_count
            model.version = proc.version
            model.status = proc.status.value
            model.is_global = proc.is_global
            model.procedure_metadata = proc.metadata
        else:
            model = LearnedProcedureModel(
                id=proc.procedure_id,
                user_id=proc.user_id,
                task_domain=proc.task_domain,
                name=proc.name,
                description=proc.description,
                trigger_conditions=proc.trigger_conditions,
                ordered_steps=proc.ordered_steps,
                required_tools=proc.required_tools,
                constraints=proc.constraints,
                success_criteria=proc.success_criteria,
                confidence=proc.confidence,
                usage_count=proc.usage_count,
                success_count=proc.success_count,
                failure_count=proc.failure_count,
                version=proc.version,
                status=proc.status.value,
                is_global=proc.is_global,
                procedure_metadata=proc.metadata,
            )
            session.add(model)
        await session.flush()

    def _model_to_trajectory(self, m: TrajectoryModel) -> ExecutionTrajectory:
        outcome = m.final_outcome
        if isinstance(outcome, dict) and "result" in outcome and len(outcome) == 1:
            outcome = outcome["result"]

        return ExecutionTrajectory(
            trajectory_id=m.id,
            task_id=m.task_id,
            run_id=m.run_id,
            user_id=m.user_id,
            goal=m.goal,
            planning_steps=m.planning_steps,
            selected_tools=m.selected_tools,
            tool_calls_metadata=m.tool_calls_metadata,
            worker_involvement=m.worker_involvement,
            intermediate_decisions=m.intermediate_decisions,
            failures=m.failures,
            retries_count=m.retries_count,
            final_outcome=outcome,
            is_success=m.is_success,
            duration_ms=m.duration_ms,
            tokens_used=m.tokens_used,
            cost_usd=m.cost_usd,
            policy_decisions=m.policy_decisions,
            evaluation_summary=m.evaluation_summary,
            created_at=m.created_at,
        )

    def _model_to_procedure(self, m: LearnedProcedureModel) -> LearnedProcedure:
        return LearnedProcedure(
            procedure_id=m.id,
            user_id=m.user_id,
            task_domain=m.task_domain,
            name=m.name,
            description=m.description,
            trigger_conditions=m.trigger_conditions,
            ordered_steps=m.ordered_steps,
            required_tools=m.required_tools,
            constraints=m.constraints,
            success_criteria=m.success_criteria,
            confidence=m.confidence,
            usage_count=m.usage_count,
            success_count=m.success_count,
            failure_count=m.failure_count,
            version=m.version,
            status=PromotionStatus(m.status),
            is_global=m.is_global,
            metadata=m.procedure_metadata,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
