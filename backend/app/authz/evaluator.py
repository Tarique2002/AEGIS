"""Evaluator for Dynamic RBAC, Scope enforcement, and Tenant Policies."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.abac.context import AuthorizationContext
from app.authz.policy import PolicyEngine
from app.authz.repository import AuthzRepository
from app.authz.roles import DEFAULT_ROLE_PERMISSIONS
from app.authz.schemas import AuthorizationDecision
from app.core.auth import AuthenticatedPrincipal


class AuthorizationEvaluator:
    """Evaluates dynamic policies, user roles, ABAC rules, and token scopes."""

    def __init__(self, repository: AuthzRepository | None = None) -> None:
        self.repository = repository or AuthzRepository()

    async def evaluate(
        self,
        principal: AuthenticatedPrincipal,
        permission: str,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        context: AuthorizationContext | None = None,
    ) -> AuthorizationDecision:
        """
        Evaluate whether the principal is authorized to perform action with permission.
        Combines dynamic tenant policies with assigned roles, ABAC rules, and CEL expressions.
        """
        # 1. Fetch effective roles and permissions for user in tenant
        roles, role_perms = await self.repository.get_user_effective_roles_and_permissions(
            user_id=principal.user_id,
            tenant_id=tenant_id,
            session=session,
        )

        # Include any system roles embedded in JWT principal claims
        for r in principal.roles:
            r_upper = r.upper()
            if r_upper in DEFAULT_ROLE_PERMISSIONS:
                role_perms.extend(DEFAULT_ROLE_PERMISSIONS[r_upper])
            if r_upper == "ADMIN" or r.lower() == "admin":
                role_perms.append("admin:*")

        # 2. Build default context if not supplied
        eval_context = context or AuthorizationContext.build(
            principal=principal,
            action=permission,
            tenant_id=tenant_id,
            resource_type="system",
            effective_roles=roles,
            effective_permissions=role_perms,
        )

        # 3. Fetch active policies for tenant
        policies = await self.repository.list_policies(tenant_id=tenant_id, session=session)

        # 4. Evaluate deterministic precedence via PolicyEngine
        return PolicyEngine.evaluate_policies(
            permission=permission,
            user_id=principal.user_id,
            tenant_id=tenant_id,
            policies=policies,
            role_permissions=role_perms,
            context=eval_context,
        )
