"""Decision Engine coordinating final safety verdicts, constraints, and approval states."""

from app.safety.schemas import (
    ApprovalStatus,
    SafetyDecision,
    SafetyDecisionType,
)


class SafetyDecisionEngine:
    """Evaluates safety verdicts and applies conditional constraints."""

    @staticmethod
    def apply_approval_state(
        decision: SafetyDecision,
        approval_status: ApprovalStatus | None,
    ) -> SafetyDecision:
        """
        Update a REQUIRE_APPROVAL safety decision based on human approval state.
        Never silently converts DENY into ALLOW.
        """
        if decision.decision_type != SafetyDecisionType.REQUIRE_APPROVAL:
            return decision

        if approval_status == ApprovalStatus.APPROVED:
            return SafetyDecision(
                decision_id=decision.decision_id,
                allowed=True,
                decision_type=SafetyDecisionType.ALLOW_WITH_CONSTRAINTS,
                risk_level=decision.risk_level,
                risk_categories=decision.risk_categories,
                reason="Action permitted via verified human approval.",
                required_approval=False,
                policy_version=decision.policy_version,
                gate_results=decision.gate_results,
                metadata={**decision.metadata, "approved": True},
            )
        elif approval_status == ApprovalStatus.DENIED:
            return SafetyDecision(
                decision_id=decision.decision_id,
                allowed=False,
                decision_type=SafetyDecisionType.DENY,
                risk_level=decision.risk_level,
                risk_categories=decision.risk_categories,
                reason="Explicit human approval was denied.",
                required_approval=False,
                policy_version=decision.policy_version,
                gate_results=decision.gate_results,
                metadata={**decision.metadata, "approval_denied": True},
            )
        elif approval_status == ApprovalStatus.EXPIRED:
            return SafetyDecision(
                decision_id=decision.decision_id,
                allowed=False,
                decision_type=SafetyDecisionType.DENY,
                risk_level=decision.risk_level,
                risk_categories=decision.risk_categories,
                reason="Approval request has expired.",
                required_approval=True,
                policy_version=decision.policy_version,
                gate_results=decision.gate_results,
                metadata={**decision.metadata, "approval_expired": True},
            )

        return decision
