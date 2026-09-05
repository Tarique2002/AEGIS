"""Controlled promotion policy and validation pipeline for candidate procedures."""

import uuid

from pydantic import BaseModel, Field

from app.learning.sanitizer import sanitize_data
from app.learning.schemas import (
    ExecutionTrajectory,
    LearnedProcedure,
    OutcomeEvaluationResult,
    ProcedureCandidate,
    ProcedurePromotionDecision,
    PromotionStatus,
)


class PromotionPolicy(BaseModel):
    """Configurable safety thresholds for procedural promotion."""

    min_evaluation_score: float = Field(default=0.85, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    min_efficiency: float = Field(default=0.70, ge=0.0, le=1.0)
    max_policy_violations: int = Field(default=0, ge=0)
    min_steps: int = Field(default=1, ge=1)
    require_zero_failures: bool = Field(default=False)


class PromotionManager:
    """
    Evaluates candidates against safety policies and promotes validated blueprints
    into authoritative learned procedures.
    """

    def __init__(self, policy: PromotionPolicy | None = None) -> None:
        self.policy = policy or PromotionPolicy()

    def create_candidate(
        self,
        trajectory: ExecutionTrajectory,
        evaluation: OutcomeEvaluationResult,
        domain: str = "general",
    ) -> ProcedureCandidate:
        """Derive a candidate procedure proposal from a completed trajectory."""
        steps = trajectory.planning_steps or []
        if not steps and trajectory.tool_calls_metadata:
            # Construct synthetic steps from tool execution sequence
            steps = [
                {
                    "step_id": i + 1,
                    "name": call.get("tool_name", f"tool_step_{i+1}"),
                    "tool": call.get("tool_name"),
                    "action": "execute_tool",
                }
                for i, call in enumerate(trajectory.tool_calls_metadata)
            ]

        # Trigger conditions derived from goal keywords/intent
        triggers = [
            f"objective_matches: {trajectory.goal[:100]}",
            f"domain_equals: {domain}",
        ]

        # Constraints
        constraints = [
            "strict_tenant_isolation",
            "enforce_tool_authorization",
        ]

        # Success criteria
        success_criteria = [
            f"completion_quality >= {self.policy.min_evaluation_score}",
            "zero_policy_violations",
        ]

        return ProcedureCandidate(
            candidate_id=uuid.uuid4(),
            trajectory_id=trajectory.trajectory_id,
            user_id=trajectory.user_id,
            task_domain=domain,
            name=f"Strategy: {trajectory.goal[:50]}",
            description=f"Auto-extracted procedural strategy for: {trajectory.goal}",
            trigger_conditions=triggers,
            ordered_steps=sanitize_data(steps),
            required_tools=list(set(trajectory.selected_tools)),
            constraints=constraints,
            success_criteria=success_criteria,
            confidence=evaluation.confidence,
            validation_errors=[],
            status=PromotionStatus.CANDIDATE,
        )

    def evaluate_and_promote(
        self,
        candidate: ProcedureCandidate,
        evaluation: OutcomeEvaluationResult,
        actor: str = "system",
        existing_procedure: LearnedProcedure | None = None,
    ) -> tuple[ProcedurePromotionDecision, LearnedProcedure | None]:
        """
        Validate candidate against promotion criteria.
        If passed, generate or update a LearnedProcedure.
        """
        errors: list[str] = []

        # 1. Verification of evaluation scores
        if evaluation.task_completion_quality < self.policy.min_evaluation_score:
            errors.append(
                f"Task completion quality {evaluation.task_completion_quality} < "
                f"required {self.policy.min_evaluation_score}"
            )

        if evaluation.confidence < self.policy.min_confidence:
            errors.append(
                f"Evaluation confidence {evaluation.confidence} < "
                f"required {self.policy.min_confidence}"
            )

        if evaluation.execution_efficiency < self.policy.min_efficiency:
            errors.append(
                f"Execution efficiency {evaluation.execution_efficiency} < "
                f"required {self.policy.min_efficiency}"
            )

        if evaluation.policy_violations > self.policy.max_policy_violations:
            errors.append(
                f"Policy violations count {evaluation.policy_violations} "
                f"exceeds threshold {self.policy.max_policy_violations}"
            )

        if not evaluation.success:
            errors.append("Execution was not successful; failed trajectories cannot be promoted.")

        # 2. Structural validation
        if len(candidate.ordered_steps) < self.policy.min_steps:
            errors.append(
                f"Candidate step count {len(candidate.ordered_steps)} < "
                f"minimum {self.policy.min_steps}"
            )

        if not candidate.name or len(candidate.name.strip()) < 3:
            errors.append("Candidate strategy name must be at least 3 characters.")

        validation_passed = len(errors) == 0

        if not validation_passed:
            decision = ProcedurePromotionDecision(
                audit_id=uuid.uuid4(),
                candidate_id=candidate.candidate_id,
                procedure_id=None,
                promoted=False,
                reason="; ".join(errors),
                actor=actor,
                evaluation_score=evaluation.task_completion_quality,
                confidence=evaluation.confidence,
                validation_passed=False,
            )
            candidate.status = PromotionStatus.REJECTED
            candidate.validation_errors = errors
            return decision, None

        # 3. Promotion
        candidate.status = PromotionStatus.PROMOTED
        if existing_procedure:
            # Upgrade existing procedure version
            new_version = existing_procedure.version + 1
            version_transition = f"v{existing_procedure.version} -> v{new_version}"
            promoted_proc = LearnedProcedure(
                procedure_id=existing_procedure.procedure_id,
                user_id=candidate.user_id,
                task_domain=candidate.task_domain,
                name=candidate.name,
                description=candidate.description,
                trigger_conditions=candidate.trigger_conditions,
                ordered_steps=candidate.ordered_steps,
                required_tools=candidate.required_tools,
                constraints=candidate.constraints,
                success_criteria=candidate.success_criteria,
                confidence=round((existing_procedure.confidence + evaluation.confidence) / 2.0, 4),
                usage_count=existing_procedure.usage_count + 1,
                success_count=existing_procedure.success_count + 1,
                failure_count=existing_procedure.failure_count,
                version=new_version,
                status=PromotionStatus.PROMOTED,
                is_global=existing_procedure.is_global,
                metadata={"source_candidate_id": str(candidate.candidate_id)},
            )
        else:
            version_transition = "v0 -> v1 (new)"
            promoted_proc = LearnedProcedure(
                procedure_id=uuid.uuid4(),
                user_id=candidate.user_id,
                task_domain=candidate.task_domain,
                name=candidate.name,
                description=candidate.description,
                trigger_conditions=candidate.trigger_conditions,
                ordered_steps=candidate.ordered_steps,
                required_tools=candidate.required_tools,
                constraints=candidate.constraints,
                success_criteria=candidate.success_criteria,
                confidence=evaluation.confidence,
                usage_count=1,
                success_count=1,
                failure_count=0,
                version=1,
                status=PromotionStatus.PROMOTED,
                is_global=False,
                metadata={"source_candidate_id": str(candidate.candidate_id)},
            )

        decision = ProcedurePromotionDecision(
            audit_id=uuid.uuid4(),
            candidate_id=candidate.candidate_id,
            procedure_id=promoted_proc.procedure_id,
            promoted=True,
            reason="All validation criteria and confidence thresholds satisfied.",
            actor=actor,
            evaluation_score=evaluation.task_completion_quality,
            confidence=evaluation.confidence,
            validation_passed=True,
            version_transition=version_transition,
        )
        return decision, promoted_proc
