"""Learning Governance Manager coordinating lifecycle, gates, rollbacks, and drift."""

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base import utc_now
from app.db.models.learning import (
    LearnedProcedureModel,
    LearnedProcedureVersionModel,
    LearningGovernanceConfigModel,
    ProcedureGovernanceEvaluationModel,
    TrajectoryModel,
)
from app.learning.governance.drift import LearningDriftDetector
from app.learning.governance.gates import DeterministicPromotionGateEngine
from app.learning.governance.regression import ProcedureRegressionEvaluator
from app.learning.governance.schemas import (
    ApprovalStatus,
    DriftReport,
    DriftStatus,
    GovernanceConfig,
    GovernanceConfigUpdate,
    GovernanceProcedureStatus,
    PromotionGateResult,
    RollbackResult,
    ShadowEvaluationResult,
)
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType

logger = get_logger("aegis.learning.governance.manager")


class LearningGovernanceManager:
    """
    Authoritative governance controller for learned strategies and procedures.
    Enforces deterministic gates, shadow evaluation, versioning, drift detection,
    safe rollback, and human approval workflows.
    """

    def __init__(
        self,
        gate_engine: DeterministicPromotionGateEngine | None = None,
        drift_detector: LearningDriftDetector | None = None,
        regression_evaluator: ProcedureRegressionEvaluator | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self.gate_engine = gate_engine or DeterministicPromotionGateEngine()
        self.drift_detector = drift_detector or LearningDriftDetector()
        self.regression_evaluator = regression_evaluator or ProcedureRegressionEvaluator()
        self.event_emitter = event_emitter or EventEmitter()

    async def get_or_create_config(
        self,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> GovernanceConfig:
        """Fetch tenant governance configuration or initialize defaults."""
        stmt = select(LearningGovernanceConfigModel).where(
            LearningGovernanceConfigModel.user_id == tenant_id
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()

        if not model:
            model = LearningGovernanceConfigModel(
                user_id=tenant_id,
                min_evaluation_count=3,
                min_success_rate=0.85,
                min_quality_score=0.80,
                min_confidence=0.80,
                max_regression_tolerance=0.05,
                require_human_approval_for_high_risk=True,
                drift_evaluation_window=20,
                drift_warning_threshold=0.10,
                drift_critical_threshold=0.20,
                config_metadata={},
            )
            session.add(model)
            await session.flush()

        return GovernanceConfig(
            min_evaluation_count=model.min_evaluation_count,
            min_success_rate=model.min_success_rate,
            min_quality_score=model.min_quality_score,
            min_confidence=model.min_confidence,
            max_regression_tolerance=model.max_regression_tolerance,
            require_human_approval_for_high_risk=model.require_human_approval_for_high_risk,
            drift_evaluation_window=model.drift_evaluation_window,
            drift_warning_threshold=model.drift_warning_threshold,
            drift_critical_threshold=model.drift_critical_threshold,
            config_metadata=model.config_metadata,
        )

    async def update_config(
        self,
        tenant_id: uuid.UUID,
        updates: GovernanceConfigUpdate,
        session: AsyncSession,
    ) -> GovernanceConfig:
        """Update tenant governance configuration."""
        stmt = select(LearningGovernanceConfigModel).where(
            LearningGovernanceConfigModel.user_id == tenant_id
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()

        if not model:
            model = LearningGovernanceConfigModel(user_id=tenant_id)
            session.add(model)

        for field, val in updates.model_dump(exclude_unset=True).items():
            if val is not None:
                setattr(model, field, val)

        await session.flush()
        return await self.get_or_create_config(tenant_id, session)

    async def validate_procedure(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PromotionGateResult:
        """
        Deterministically validate candidate procedure against configured promotion gates.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        cfg = await self.get_or_create_config(tenant_id, session)

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_VALIDATION_STARTED,
            payload={"procedure_id": str(procedure_id), "tenant_id": str(tenant_id)},
            session=session,
        )

        result = self.gate_engine.evaluate_gates(proc, config=cfg)

        # Update procedure status
        if result.passed:
            proc.status = GovernanceProcedureStatus.VALIDATED.value
        elif result.is_blocked_by_approval:
            proc.status = GovernanceProcedureStatus.PENDING_APPROVAL.value
            proc.approval_status = ApprovalStatus.PENDING.value
        else:
            proc.status = GovernanceProcedureStatus.REJECTED.value

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_VALIDATION_COMPLETED,
            payload={
                "procedure_id": str(procedure_id),
                "passed": result.passed,
                "status": proc.status,
                "reason": result.reason,
            },
            session=session,
        )

        await session.flush()
        return result

    async def request_promotion(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        actor: str = "operator",
    ) -> PromotionGateResult:
        """
        Request procedure promotion through deterministic gates.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        cfg = await self.get_or_create_config(tenant_id, session)

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_PROMOTION_REQUESTED,
            payload={
                "procedure_id": str(procedure_id),
                "tenant_id": str(tenant_id),
                "actor": actor,
            },
            session=session,
        )

        result = self.gate_engine.evaluate_gates(proc, config=cfg)

        if result.passed:
            proc.status = GovernanceProcedureStatus.VALIDATED.value
        elif result.is_blocked_by_approval:
            proc.status = GovernanceProcedureStatus.PENDING_APPROVAL.value
            proc.approval_status = ApprovalStatus.PENDING.value
        else:
            proc.status = GovernanceProcedureStatus.REJECTED.value

        await session.flush()
        return result

    async def approve_promotion(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        approver: str = "operator",
        reason: str = "Human review approved",
    ) -> bool:
        """
        Record explicit human approval for high-risk procedure promotion.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        proc.approval_status = ApprovalStatus.APPROVED.value
        proc.approved_by = approver
        proc.approved_at = utc_now()
        if proc.status == GovernanceProcedureStatus.PENDING_APPROVAL.value:
            proc.status = GovernanceProcedureStatus.VALIDATED.value

        meta = proc.provenance_metadata or {}
        meta["approval_reason"] = reason
        proc.provenance_metadata = meta

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_PROMOTION_APPROVED,
            payload={
                "procedure_id": str(procedure_id),
                "approver": approver,
                "reason": reason,
            },
            session=session,
        )
        await session.flush()
        return True

    async def reject_promotion(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        actor: str = "operator",
        reason: str = "Rejected by governance policy",
    ) -> bool:
        """
        Explicitly reject candidate procedure promotion.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        proc.approval_status = ApprovalStatus.REJECTED.value
        proc.status = GovernanceProcedureStatus.REJECTED.value

        meta = proc.provenance_metadata or {}
        meta["rejection_reason"] = reason
        proc.provenance_metadata = meta

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_PROMOTION_REJECTED,
            payload={
                "procedure_id": str(procedure_id),
                "actor": actor,
                "reason": reason,
            },
            session=session,
        )
        await session.flush()
        return True

    async def promote_procedure(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        actor: str = "system",
    ) -> LearnedProcedureModel:
        """
        Promote candidate procedure into active production after gate verification.
        Preserves snapshot in learned_procedure_versions table.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        cfg = await self.get_or_create_config(tenant_id, session)
        gate_result = self.gate_engine.evaluate_gates(proc, config=cfg)

        if not gate_result.passed:
            raise ValueError(f"Promotion rejected: {gate_result.reason}")

        # Record version snapshot before/as part of promotion
        snapshot_data = self._create_procedure_snapshot(proc)
        version_record = LearnedProcedureVersionModel(
            id=uuid.uuid4(),
            procedure_id=proc.id,
            user_id=tenant_id,
            version=proc.version,
            status=GovernanceProcedureStatus.PROMOTED.value,
            snapshot=snapshot_data,
            validation_score=proc.validation_score,
            confidence=proc.confidence,
            safety_classification=proc.safety_classification,
            rollback_reason=None,
            created_at=utc_now(),
        )
        session.add(version_record)

        proc.status = GovernanceProcedureStatus.PROMOTED.value
        proc.promoted_at = utc_now()

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_PROCEDURE_PROMOTED,
            payload={
                "procedure_id": str(proc.id),
                "version": proc.version,
                "actor": actor,
            },
            session=session,
        )

        await session.flush()
        return proc

    async def disable_procedure(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        reason: str = "Administrative disable",
        actor: str = "operator",
    ) -> bool:
        """
        Disable an active procedure without deleting historical records.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        proc.status = GovernanceProcedureStatus.DISABLED.value
        meta = proc.provenance_metadata or {}
        meta["disabled_reason"] = reason
        meta["disabled_at"] = utc_now().isoformat()
        meta["disabled_by"] = actor
        proc.provenance_metadata = meta

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_PROCEDURE_DISABLED,
            payload={
                "procedure_id": str(procedure_id),
                "reason": reason,
                "actor": actor,
            },
            session=session,
        )
        await session.flush()
        return True

    async def rollback_procedure(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        target_version: int | None = None,
        reason: str = "Regression rollback",
        actor: str = "operator",
    ) -> RollbackResult:
        """
        Safely roll back a procedure to a previous known-good version snapshot.
        Preserves audit history and provenance.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        current_ver = proc.version

        # Find target snapshot in version history
        stmt = (
            select(LearnedProcedureVersionModel)
            .where(
                LearnedProcedureVersionModel.procedure_id == procedure_id,
                LearnedProcedureVersionModel.user_id == tenant_id,
            )
            .order_by(desc(LearnedProcedureVersionModel.version))
        )
        if target_version is not None:
            stmt = stmt.where(LearnedProcedureVersionModel.version == target_version)
        else:
            # Look for previous version strictly less than current_ver
            stmt = stmt.where(LearnedProcedureVersionModel.version < current_ver)

        res = await session.execute(stmt)
        snapshot_model = res.scalars().first()

        if not snapshot_model:
            raise ValueError(
                f"No previous version snapshot available for procedure '{procedure_id}'."
            )

        restored_ver = snapshot_model.version
        snapshot = snapshot_model.snapshot

        # Restore tactical state from snapshot
        proc.name = snapshot.get("name", proc.name)
        proc.description = snapshot.get("description", proc.description)
        proc.trigger_conditions = snapshot.get("trigger_conditions", proc.trigger_conditions)
        proc.ordered_steps = snapshot.get("ordered_steps", proc.ordered_steps)
        proc.required_tools = snapshot.get("required_tools", proc.required_tools)
        proc.constraints = snapshot.get("constraints", proc.constraints)
        proc.success_criteria = snapshot.get("success_criteria", proc.success_criteria)
        proc.confidence = snapshot_model.confidence
        proc.validation_score = snapshot_model.validation_score
        proc.status = GovernanceProcedureStatus.ROLLED_BACK.value
        proc.parent_procedure_id = proc.id
        proc.parent_version = current_ver

        meta = proc.provenance_metadata or {}
        meta["last_rollback"] = {
            "from_version": current_ver,
            "restored_to_version": restored_ver,
            "reason": reason,
            "actor": actor,
            "timestamp": utc_now().isoformat(),
        }
        proc.provenance_metadata = meta

        # Record rollback version snapshot
        new_version_record = LearnedProcedureVersionModel(
            id=uuid.uuid4(),
            procedure_id=proc.id,
            user_id=tenant_id,
            version=current_ver + 1,
            status=GovernanceProcedureStatus.ROLLED_BACK.value,
            snapshot=self._create_procedure_snapshot(proc),
            validation_score=proc.validation_score,
            confidence=proc.confidence,
            safety_classification=proc.safety_classification,
            rollback_reason=reason,
            created_at=utc_now(),
        )
        proc.version = current_ver + 1
        session.add(new_version_record)

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_PROCEDURE_ROLLBACK,
            payload={
                "procedure_id": str(procedure_id),
                "from_version": current_ver,
                "restored_to_version": restored_ver,
                "reason": reason,
                "actor": actor,
            },
            session=session,
        )

        await session.flush()
        return RollbackResult(
            procedure_id=procedure_id,
            rolled_back_from_version=current_ver,
            restored_to_version=restored_ver,
            status=GovernanceProcedureStatus.ROLLED_BACK,
            reason=reason,
            actor=actor,
        )

    async def check_drift(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> DriftReport:
        """
        Evaluate real-time learning drift against historical execution trajectories.
        """
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        cfg = await self.get_or_create_config(tenant_id, session)

        # Retrieve trailing window of trajectories for this tenant
        traj_stmt = (
            select(TrajectoryModel)
            .where(TrajectoryModel.user_id == tenant_id)
            .order_by(desc(TrajectoryModel.created_at))
            .limit(cfg.drift_evaluation_window)
        )
        res = await session.execute(traj_stmt)
        trajectories = list(res.scalars().all())

        report = self.drift_detector.assess_drift(proc, trajectories, config=cfg)

        if report.drift_status == DriftStatus.CRITICAL:
            await self.event_emitter.emit(
                task_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                event_type=ExecutionEventType.GOVERNANCE_DRIFT_CRITICAL,
                payload={
                    "procedure_id": str(procedure_id),
                    "status": report.drift_status.value,
                    "issues": report.detected_issues,
                },
                session=session,
            )
        elif report.drift_status in (DriftStatus.WARNING, DriftStatus.DEGRADED):
            await self.event_emitter.emit(
                task_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
                event_type=ExecutionEventType.GOVERNANCE_DRIFT_WARNING,
                payload={
                    "procedure_id": str(procedure_id),
                    "status": report.drift_status.value,
                    "issues": report.detected_issues,
                },
                session=session,
            )

        return report

    async def run_shadow_evaluation(
        self,
        candidate_id: uuid.UUID,
        baseline_id: uuid.UUID | None,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        sample_limit: int = 10,
    ) -> ShadowEvaluationResult:
        """
        Replay candidate strategy vs baseline across representative sanitized trajectories.
        """
        candidate = await self._get_tenant_procedure(candidate_id, tenant_id, session)
        if not candidate:
            raise ValueError(f"Candidate procedure '{candidate_id}' not found for tenant.")

        baseline = None
        if baseline_id:
            baseline = await self._get_tenant_procedure(baseline_id, tenant_id, session)

        cfg = await self.get_or_create_config(tenant_id, session)

        # Load representative historical trajectories
        traj_stmt = (
            select(TrajectoryModel)
            .where(TrajectoryModel.user_id == tenant_id)
            .order_by(desc(TrajectoryModel.created_at))
            .limit(sample_limit)
        )
        res = await session.execute(traj_stmt)
        trajectories = list(res.scalars().all())

        result = self.regression_evaluator.evaluate_shadow(
            candidate=candidate,
            baseline=baseline,
            trajectories=trajectories,
            config=cfg,
        )

        # Persist audit record of evaluation
        eval_record = ProcedureGovernanceEvaluationModel(
            id=result.evaluation_id,
            user_id=tenant_id,
            baseline_procedure_id=baseline_id,
            candidate_procedure_id=candidate_id,
            evaluation_type="SHADOW",
            baseline_metrics=result.baseline_metrics,
            candidate_metrics=result.candidate_metrics,
            metric_deltas=result.metric_deltas,
            regression_detected=result.regression_detected,
            promotion_recommended=result.promotion_recommended,
            status=result.status,
        )
        session.add(eval_record)

        await self.event_emitter.emit(
            task_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.GOVERNANCE_REGRESSION_EVALUATED,
            payload={
                "candidate_id": str(candidate_id),
                "baseline_id": str(baseline_id) if baseline_id else None,
                "regression_detected": result.regression_detected,
                "promotion_recommended": result.promotion_recommended,
            },
            session=session,
        )

        await session.flush()
        return result

    async def list_version_history(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[LearnedProcedureVersionModel]:
        """Fetch full immutable version snapshot history for a procedure."""
        # Ensure procedure belongs to tenant
        proc = await self._get_tenant_procedure(procedure_id, tenant_id, session)
        if not proc:
            raise ValueError(f"Procedure '{procedure_id}' not found for tenant.")

        stmt = (
            select(LearnedProcedureVersionModel)
            .where(
                LearnedProcedureVersionModel.procedure_id == procedure_id,
                LearnedProcedureVersionModel.user_id == tenant_id,
            )
            .order_by(desc(LearnedProcedureVersionModel.version))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def _get_tenant_procedure(
        self,
        procedure_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> LearnedProcedureModel | None:
        """Fetch procedure strictly enforcing tenant isolation."""
        stmt = select(LearnedProcedureModel).where(
            LearnedProcedureModel.id == procedure_id,
            LearnedProcedureModel.user_id == tenant_id,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    def _create_procedure_snapshot(self, proc: LearnedProcedureModel) -> dict[str, Any]:
        return {
            "procedure_id": str(proc.id),
            "name": proc.name,
            "task_domain": proc.task_domain,
            "description": proc.description,
            "trigger_conditions": proc.trigger_conditions,
            "ordered_steps": proc.ordered_steps,
            "required_tools": proc.required_tools,
            "constraints": proc.constraints,
            "success_criteria": proc.success_criteria,
            "confidence": proc.confidence,
            "validation_score": proc.validation_score,
            "version": proc.version,
            "safety_classification": proc.safety_classification,
            "source_trajectory_ids": proc.source_trajectory_ids,
            "source_evaluation_ids": proc.source_evaluation_ids,
        }
