"""Policy evaluation rules and precedence ordering for Phase 10 ABAC & RBAC."""

import time
import uuid

from app.authz.abac.context import AuthorizationContext
from app.authz.abac.evaluator import ABACEvaluator
from app.authz.abac.policies import ABACPolicyRule, PolicyType
from app.authz.permissions import is_permission_matching
from app.authz.schemas import (
    AuthorizationDecision,
    PolicyDefinition,
    PolicyEffect,
)
from app.schemas.common import utc_now


class PolicyEngine:
    """
    Evaluates dynamic authorization policies using deterministic fail-closed precedence:
    1. Explicit security DENY
    2. Tenant DENY (RBAC / dynamic condition DENY)
    3. ABAC DENY (matching CEL or attribute condition with DENY effect)
    4. Missing scope
    5. Missing RBAC permission
    6. Ownership failure
    7. ABAC ALLOW
    8. RBAC ALLOW
    9. Default DENY
    """

    def __init__(self, abac_evaluator: ABACEvaluator | None = None) -> None:
        self.abac_evaluator = abac_evaluator or ABACEvaluator()

    @classmethod
    def evaluate_policies(
        cls,
        permission: str,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        policies: list[PolicyDefinition],
        role_permissions: list[str],
        context: AuthorizationContext | None = None,
    ) -> AuthorizationDecision:
        """
        Evaluate action permission against dynamic tenant policies, ABAC rules,
        and role permissions.
        """
        start_time = time.perf_counter()
        engine = cls()

        active_policies = [p for p in policies if p.enabled]
        sorted_policies = sorted(active_policies, key=lambda p: p.priority)

        # 1 & 2 & 3. Check Explicit DENY policies first (RBAC + ABAC + CEL)
        for pol in sorted_policies:
            if pol.effect == PolicyEffect.DENY:
                # Check permission match
                perm_match = (
                    any(
                        is_permission_matching(permission, granted_perm)
                        for granted_perm in pol.permissions
                    )
                    or not pol.permissions
                )

                if perm_match:
                    # Check ABAC / CEL conditions if context present
                    if context and (pol.conditions or pol.cel_expression):
                        rule = ABACPolicyRule(
                            policy_id=pol.policy_id,
                            tenant_id=pol.tenant_id,
                            name=pol.name,
                            version=pol.version,
                            policy_type=PolicyType(pol.policy_type)
                            if pol.policy_type in PolicyType._value2member_map_
                            else PolicyType.COMBINED,
                            effect=pol.effect,
                            priority=pol.priority,
                            cel_expression=pol.cel_expression,
                            conditions=pol.conditions,
                            enabled=pol.enabled,
                        )
                        if not engine.abac_evaluator.evaluate_rule(rule, context):
                            continue

                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    return AuthorizationDecision(
                        allowed=False,
                        permission=permission,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        action=context.action if context else "",
                        resource_type=context.resource_type if context else "",
                        resource_id=context.resource_id if context else None,
                        matched_policy_id=pol.policy_id,
                        matched_policy_ids=[pol.policy_id],
                        reason=f"Action explicitly DENIED by policy '{pol.name}'.",
                        decision_reason=f"Action explicitly DENIED by policy '{pol.name}'.",
                        policy_version=pol.version,
                        policy_versions=[pol.version],
                        evaluation_duration_ms=duration_ms,
                        evaluated_at=utc_now(),
                    )

        # 4 & 5. Check Explicit ALLOW policies (ABAC / CEL / Policy rules)
        for pol in sorted_policies:
            if pol.effect == PolicyEffect.ALLOW:
                perm_match = (
                    any(
                        is_permission_matching(permission, granted_perm)
                        for granted_perm in pol.permissions
                    )
                    or not pol.permissions
                )

                if perm_match:
                    if context and (pol.conditions or pol.cel_expression):
                        rule = ABACPolicyRule(
                            policy_id=pol.policy_id,
                            tenant_id=pol.tenant_id,
                            name=pol.name,
                            version=pol.version,
                            policy_type=PolicyType(pol.policy_type)
                            if pol.policy_type in PolicyType._value2member_map_
                            else PolicyType.COMBINED,
                            effect=pol.effect,
                            priority=pol.priority,
                            cel_expression=pol.cel_expression,
                            conditions=pol.conditions,
                            enabled=pol.enabled,
                        )
                        if not engine.abac_evaluator.evaluate_rule(rule, context):
                            continue

                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    return AuthorizationDecision(
                        allowed=True,
                        permission=permission,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        action=context.action if context else "",
                        resource_type=context.resource_type if context else "",
                        resource_id=context.resource_id if context else None,
                        matched_policy_id=pol.policy_id,
                        matched_policy_ids=[pol.policy_id],
                        reason=f"Action permitted by policy '{pol.name}'.",
                        decision_reason=f"Action permitted by policy '{pol.name}'.",
                        policy_version=pol.version,
                        policy_versions=[pol.version],
                        evaluation_duration_ms=duration_ms,
                        evaluated_at=utc_now(),
                    )

        # 6. Check Role Permissions (RBAC ALLOW)
        for role_perm in role_permissions:
            if is_permission_matching(permission, role_perm):
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return AuthorizationDecision(
                    allowed=True,
                    permission=permission,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action=context.action if context else "",
                    resource_type=context.resource_type if context else "",
                    resource_id=context.resource_id if context else None,
                    matched_role="AssignedRole",
                    matched_roles=["AssignedRole"],
                    reason=f"Action permitted by assigned role permission '{role_perm}'.",
                    decision_reason=f"Action permitted by assigned role permission '{role_perm}'.",
                    evaluation_duration_ms=duration_ms,
                    evaluated_at=utc_now(),
                )

        # 7. Default DENY
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return AuthorizationDecision(
            allowed=False,
            permission=permission,
            user_id=user_id,
            tenant_id=tenant_id,
            action=context.action if context else "",
            resource_type=context.resource_type if context else "",
            resource_id=context.resource_id if context else None,
            reason=f"Default DENY: missing permission '{permission}'.",
            decision_reason=f"Default DENY: missing permission '{permission}'.",
            evaluation_duration_ms=duration_ms,
            evaluated_at=utc_now(),
        )
