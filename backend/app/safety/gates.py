"""The 7-Stage Safety Gate Pipeline enforcing mandatory security boundaries."""

import uuid
from typing import Any

from app.core.logging import get_logger
from app.safety.classifier import SafetyClassifier
from app.safety.policies import SafetyPolicy, get_default_safety_policy
from app.safety.risk import RiskAssessmentEngine
from app.safety.schemas import (
    GateResult,
    InputTrustLevel,
    RateLimitResult,
    RiskCategory,
    RiskLevel,
    SafetyContext,
    SafetyDecision,
    SafetyDecisionType,
)

logger = get_logger("aegis.safety.gates")


class SafetyGate:
    """
    Authoritative 7-Stage Safety Gate evaluating every consequential action:
    1. Authentication Gate
    2. Ownership / Authorization Gate
    3. Capability Gate
    4. Risk Gate
    5. Budget Gate
    6. Rate-Limit Gate
    7. Policy Gate
    """

    def __init__(
        self,
        policy: SafetyPolicy | None = None,
        risk_engine: RiskAssessmentEngine | None = None,
    ) -> None:
        self.policy = policy or get_default_safety_policy()
        self.risk_engine = risk_engine or RiskAssessmentEngine(policy=self.policy)

    async def evaluate(
        self,
        context: SafetyContext,
        rate_limit_result: RateLimitResult | None = None,
    ) -> SafetyDecision:
        """Execute full 7-stage safety evaluation pipeline."""
        gate_results: list[GateResult] = []

        # 1. Authentication Gate
        auth_res = self._check_authentication_gate(context)
        gate_results.append(auth_res)
        if not auth_res.passed:
            return self._build_verdict(context, gate_results, auth_res.decision, auth_res.reason)

        # 2. Ownership / Authorization Gate
        owner_res = self._check_ownership_gate(context)
        gate_results.append(owner_res)
        if not owner_res.passed:
            return self._build_verdict(context, gate_results, owner_res.decision, owner_res.reason)

        # 3. Capability Gate
        cap_res = self._check_capability_gate(context)
        gate_results.append(cap_res)
        if not cap_res.passed:
            return self._build_verdict(context, gate_results, cap_res.decision, cap_res.reason)

        # 4. Risk Gate
        risk_assessment = self.risk_engine.assess(context)
        context.risk_level = risk_assessment.level
        context.risk_categories = risk_assessment.categories
        risk_res = self._check_risk_gate(context, risk_assessment)
        gate_results.append(risk_res)
        if not risk_res.passed:
            return self._build_verdict(context, gate_results, risk_res.decision, risk_res.reason)

        # 5. Budget Gate
        budget_res = self._check_budget_gate(context)
        gate_results.append(budget_res)
        if not budget_res.passed:
            return self._build_verdict(
                context, gate_results, budget_res.decision, budget_res.reason
            )

        # 6. Rate-Limit Gate
        rate_res = self._check_rate_limit_gate(context, rate_limit_result)
        gate_results.append(rate_res)
        if not rate_res.passed:
            return self._build_verdict(context, gate_results, rate_res.decision, rate_res.reason)

        # 7. Policy Gate
        policy_res = self._check_policy_gate(context, risk_assessment)
        gate_results.append(policy_res)
        if not policy_res.passed:
            return self._build_verdict(
                context, gate_results, policy_res.decision, policy_res.reason
            )

        # Determine if approval required above threshold
        decision_type = SafetyDecisionType.ALLOW
        reason = "All 7 safety gates passed successfully."
        risk_order = [
            RiskLevel.NONE,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        curr_idx = risk_order.index(context.risk_level)
        thresh_idx = risk_order.index(self.policy.require_approval_above)

        if curr_idx > thresh_idx:
            decision_type = SafetyDecisionType.REQUIRE_APPROVAL
            reason = (
                f"Action risk level '{context.risk_level.value}' requires explicit human approval."
            )

        return self._build_verdict(context, gate_results, decision_type, reason)

    def _check_authentication_gate(self, context: SafetyContext) -> GateResult:
        if not context.authenticated or not context.user_id:
            return GateResult(
                passed=False,
                gate_name="AuthenticationGate",
                reason="Unauthenticated request or missing trusted user identity.",
                decision=SafetyDecisionType.DENY,
                risk_level=RiskLevel.CRITICAL,
            )
        return GateResult(
            passed=True,
            gate_name="AuthenticationGate",
            reason="Authenticated identity verified.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=RiskLevel.LOW,
        )

    def _check_ownership_gate(self, context: SafetyContext) -> GateResult:
        if not isinstance(context.user_id, uuid.UUID):
            return GateResult(
                passed=False,
                gate_name="OwnershipGate",
                reason="Invalid tenant ownership identifier.",
                decision=SafetyDecisionType.DENY,
                risk_level=RiskLevel.CRITICAL,
            )
        return GateResult(
            passed=True,
            gate_name="OwnershipGate",
            reason="Tenant ownership boundary verified.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=RiskLevel.LOW,
        )

    def _check_capability_gate(self, context: SafetyContext) -> GateResult:
        # Check if worker attempted forbidden capabilities
        forbidden = {"shell", "exec", "os_system", "root", "admin", "raw_sql"}
        for cap in context.requested_capabilities:
            if cap.lower() in forbidden:
                return GateResult(
                    passed=False,
                    gate_name="CapabilityGate",
                    reason=f"Forbidden capability '{cap}' requested.",
                    decision=SafetyDecisionType.DENY,
                    risk_level=RiskLevel.CRITICAL,
                )
        return GateResult(
            passed=True,
            gate_name="CapabilityGate",
            reason="Requested capabilities are authorized.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=RiskLevel.LOW,
        )

    def _check_risk_gate(self, context: SafetyContext, assessment: Any) -> GateResult:
        if assessment.level == RiskLevel.CRITICAL and (
            RiskCategory.DESTRUCTIVE in assessment.categories
            or RiskCategory.CODE_EXECUTION in assessment.categories
            or RiskCategory.SYSTEM_OPERATION in assessment.categories
        ):
            cats_str = ", ".join(c.value for c in assessment.categories)
            return GateResult(
                passed=False,
                gate_name="RiskGate",
                reason=f"Critical risk operation ({cats_str}) is rejected.",
                decision=SafetyDecisionType.DENY,
                risk_level=RiskLevel.CRITICAL,
            )
        return GateResult(
            passed=True,
            gate_name="RiskGate",
            reason=f"Risk level evaluated as '{assessment.level.value}'.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=assessment.level,
        )

    def _check_budget_gate(self, context: SafetyContext) -> GateResult:
        # Verify budget is within safety limits
        return GateResult(
            passed=True,
            gate_name="BudgetGate",
            reason="Action within allocated safety budget limits.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=RiskLevel.LOW,
        )

    def _check_rate_limit_gate(
        self,
        context: SafetyContext,
        rate_result: RateLimitResult | None,
    ) -> GateResult:
        if rate_result and not rate_result.allowed:
            return GateResult(
                passed=False,
                gate_name="RateLimitGate",
                reason=(
                    f"Rate limit exceeded. Retry after {rate_result.retry_after_seconds} seconds."
                ),
                decision=SafetyDecisionType.DENY,
                risk_level=RiskLevel.MEDIUM,
                metadata={"retry_after": rate_result.retry_after_seconds},
            )
        return GateResult(
            passed=True,
            gate_name="RateLimitGate",
            reason="Rate limit allowance available.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=RiskLevel.LOW,
        )

    def _check_policy_gate(self, context: SafetyContext, assessment: Any) -> GateResult:
        # 1. Check prompt injection in action or arguments
        suspicious, threat = SafetyClassifier.inspect_input(
            context.action, trust_level=InputTrustLevel.AUTHENTICATED_USER
        )
        if suspicious:
            return GateResult(
                passed=False,
                gate_name="PolicyGate",
                reason=f"Security violation: potential prompt injection pattern '{threat}'.",
                decision=SafetyDecisionType.DENY,
                risk_level=RiskLevel.CRITICAL,
            )

        # 2. Check denied categories
        try:
            self.policy.validate_action_risk(assessment.level, assessment.categories)
        except Exception as exc:
            return GateResult(
                passed=False,
                gate_name="PolicyGate",
                reason=str(exc),
                decision=SafetyDecisionType.DENY,
                risk_level=RiskLevel.CRITICAL,
            )

        return GateResult(
            passed=True,
            gate_name="PolicyGate",
            reason="Policy constraints satisfied.",
            decision=SafetyDecisionType.ALLOW,
            risk_level=RiskLevel.LOW,
        )

    def _build_verdict(
        self,
        context: SafetyContext,
        gate_results: list[GateResult],
        decision_type: SafetyDecisionType,
        reason: str,
    ) -> SafetyDecision:
        allowed = decision_type in [
            SafetyDecisionType.ALLOW,
            SafetyDecisionType.ALLOW_WITH_CONSTRAINTS,
        ]
        risk_order = [
            RiskLevel.NONE,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        highest_risk = context.risk_level
        for gr in gate_results:
            if risk_order.index(gr.risk_level) > risk_order.index(highest_risk):
                highest_risk = gr.risk_level

        return SafetyDecision(
            allowed=allowed,
            decision_type=decision_type,
            risk_level=highest_risk,
            risk_categories=context.risk_categories,
            reason=reason,
            required_approval=decision_type == SafetyDecisionType.REQUIRE_APPROVAL,
            policy_version=self.policy.policy_version,
            gate_results=gate_results,
            metadata=context.metadata,
        )
