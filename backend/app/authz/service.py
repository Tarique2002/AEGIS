"""Centralized AuthorizationService for Dynamic RBAC, Policies, and Scopes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.abac.cache import CompiledPolicyCache
from app.authz.abac.context import AuthorizationContext
from app.authz.cel.compiler import CELCompiler
from app.authz.evaluator import AuthorizationEvaluator
from app.authz.repository import AuthzRepository
from app.authz.schemas import (
    AuthorizationDecision,
    EffectiveAuthorizationResponse,
    PolicyCreate,
    PolicyDefinition,
    PolicySimulationRequest,
    PolicySimulationResponse,
    PolicyUpdate,
    PolicyValidationRequest,
    PolicyValidationResponse,
    PolicyVersion,
    Role,
    RoleCreate,
    UserRoleAssignment,
    UserRoleAssignmentCreate,
)
from app.core.auth import AuthenticatedPrincipal
from app.core.errors import (
    AegisNotFoundError,
    PermissionDeniedError,
    PolicyDeniedError,
    ScopeRequiredError,
)
from app.core.logging import get_logger
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType
from app.security.audit_chain import AuditChainManager

logger = get_logger("aegis.authz.service")


class AuthorizationService:
    """Production authorization service managing RBAC, ABAC, scopes, and dynamic policies."""

    def __init__(
        self,
        repository: AuthzRepository | None = None,
        evaluator: AuthorizationEvaluator | None = None,
        event_emitter: EventEmitter | None = None,
        cel_compiler: CELCompiler | None = None,
        policy_cache: CompiledPolicyCache | None = None,
    ) -> None:
        self.repository = repository or AuthzRepository()
        self.evaluator = evaluator or AuthorizationEvaluator(self.repository)
        self.event_emitter = event_emitter or EventEmitter()
        self.cel_compiler = cel_compiler or CELCompiler()
        self.policy_cache = policy_cache or CompiledPolicyCache()

    # ==========================================================================
    # Token Scope Validation
    # ==========================================================================

    @staticmethod
    def check_scope(principal: AuthenticatedPrincipal, required_scope: str) -> bool:
        """
        Check if the token has the required OAuth/token scope.
        Backward-compatible: If token has no scopes declared and is not an admin-specific
        enforcement, it permits basic operations. If scopes are present, strictly enforces.
        'admin' scope grants all scopes.
        """
        if not principal.is_authenticated:
            return False

        # If token has scopes list populated
        if principal.scopes:
            if "admin" in principal.scopes:
                return True
            return required_scope in principal.scopes

        # If user has admin role in claims, grant scope
        if "admin" in [r.lower() for r in principal.roles]:
            return True

        # Backward compatibility for legacy test/dev tokens with empty scopes list:
        # allow standard user operations, require explicit scope for admin operations
        if required_scope.startswith("admin") or required_scope in [
            "policy:write",
            "role:manage",
        ]:
            return False
        return True

    def require_scope(self, principal: AuthenticatedPrincipal, required_scope: str) -> None:
        """Enforce that principal has required token scope, raising ScopeRequiredError."""
        if not self.check_scope(principal, required_scope):
            logger.warning(
                f"Scope verification failed for user {principal.user_id}: "
                f"missing scope '{required_scope}', has {principal.scopes}"
            )
            raise ScopeRequiredError(
                f"Missing required token scope '{required_scope}'.",
                details={"required_scope": required_scope, "present_scopes": principal.scopes},
            )

    # ==========================================================================
    # Permission & Policy Evaluation
    # ==========================================================================

    async def evaluate_permission(
        self,
        principal: AuthenticatedPrincipal,
        permission: str,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        context: AuthorizationContext | None = None,
    ) -> AuthorizationDecision:
        """Evaluate permission against dynamic RBAC, ABAC rules, and tenant policies."""
        return await self.evaluator.evaluate(
            principal=principal,
            permission=permission,
            tenant_id=tenant_id,
            session=session,
            context=context,
        )

    async def require_permission(
        self,
        principal: AuthenticatedPrincipal,
        permission: str,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        context: AuthorizationContext | None = None,
    ) -> AuthorizationDecision:
        """Enforce permission, raising PermissionDeniedError or PolicyDeniedError if denied."""
        decision = await self.evaluate_permission(
            principal=principal,
            permission=permission,
            tenant_id=tenant_id,
            session=session,
            context=context,
        )
        if not decision.allowed:
            logger.warning(
                f"Authorization denied for user {principal.user_id} on '{permission}': "
                f"{decision.reason}"
            )
            if decision.matched_policy_id:
                raise PolicyDeniedError(
                    decision.reason,
                    details={
                        "permission": permission,
                        "policy_id": str(decision.matched_policy_id),
                    },
                )
            raise PermissionDeniedError(
                decision.reason,
                details={"permission": permission},
            )
        return decision

    async def get_effective_authorization(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> EffectiveAuthorizationResponse:
        """Fetch effective roles, permissions, and scopes for the caller."""
        roles, perms = await self.repository.get_user_effective_roles_and_permissions(
            user_id=principal.user_id,
            tenant_id=tenant_id,
            session=session,
        )
        if "admin" in [r.lower() for r in principal.roles]:
            roles.append("ADMIN")
            perms.append("admin:*")

        return EffectiveAuthorizationResponse(
            user_id=principal.user_id,
            roles=sorted(set(roles)),
            permissions=sorted(set(perms)),
            scopes=principal.scopes,
            is_authenticated=principal.is_authenticated,
        )

    # ==========================================================================
    # Role & Assignment Administration
    # ==========================================================================

    async def list_roles(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[Role]:
        await self.require_permission(principal, "role:read", tenant_id, session)
        return await self.repository.list_roles(tenant_id, session)

    async def create_role(
        self,
        principal: AuthenticatedPrincipal,
        data: RoleCreate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> Role:
        self.require_scope(principal, "policy:write")
        await self.require_permission(principal, "role:manage", tenant_id, session)
        role = await self.repository.create_role(data, tenant_id, session)

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type="ROLE_CREATED",
            action="create_role",
            resource_type="authz_role",
            resource_id=str(role.role_id),
            payload={"name": role.name, "permissions": role.permissions},
            session=session,
        )
        return role

    async def create_role_assignment(
        self,
        principal: AuthenticatedPrincipal,
        data: UserRoleAssignmentCreate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> UserRoleAssignment:
        self.require_scope(principal, "policy:write")
        await self.require_permission(principal, "role:manage", tenant_id, session)
        assignment = await self.repository.create_role_assignment(
            data=data,
            tenant_id=tenant_id,
            assigned_by=principal.user_id,
            session=session,
        )

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type=ExecutionEventType.ROLE_ASSIGNED.value,
            action="assign_role",
            resource_type="authz_role_assignment",
            resource_id=str(assignment.assignment_id),
            payload={
                "target_user_id": str(data.user_id),
                "role_id": str(data.role_id),
                "expires_at": str(data.expires_at) if data.expires_at else None,
            },
            session=session,
        )
        return assignment

    async def delete_role_assignment(
        self,
        principal: AuthenticatedPrincipal,
        assignment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        self.require_scope(principal, "policy:write")
        await self.require_permission(principal, "role:manage", tenant_id, session)
        await self.repository.delete_role_assignment(assignment_id, tenant_id, session)

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type=ExecutionEventType.ROLE_REVOKED.value,
            action="revoke_role_assignment",
            resource_type="authz_role_assignment",
            resource_id=str(assignment_id),
            payload={"assignment_id": str(assignment_id)},
            session=session,
        )

    # ==========================================================================
    # Dynamic Policy Administration & CEL Validation / Simulation
    # ==========================================================================

    def validate_policy(self, data: PolicyValidationRequest) -> PolicyValidationResponse:
        """Validate a policy expression without persisting it."""
        errors: list[str] = []
        warnings: list[str] = []

        if data.cel_expression:
            comp_res = self.cel_compiler.compile(data.cel_expression)
            if not comp_res.valid:
                errors.extend(comp_res.errors)

        return PolicyValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    async def simulate_policy(
        self,
        principal: AuthenticatedPrincipal,
        request: PolicySimulationRequest,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PolicySimulationResponse:
        """Simulate policy evaluation on a sample context without executing resource action."""
        self.require_scope(principal, "policy:read")
        await self.require_permission(principal, "policy:read", tenant_id, session)

        context = AuthorizationContext.build(
            principal=principal,
            action=request.action,
            tenant_id=tenant_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            resource_owner_id=request.resource_owner_id,
            resource_sensitivity=request.resource_sensitivity,
            resource_risk_level=request.resource_risk_level,
            request_params=request.request_params,
        )

        decision = await self.evaluate_permission(
            principal=principal,
            permission=request.permission,
            tenant_id=tenant_id,
            session=session,
            context=context,
        )

        matched_policy_name = None
        policy_type = None
        if decision.matched_policy_id:
            pol = await self.repository.get_policy(decision.matched_policy_id, tenant_id, session)
            if pol:
                matched_policy_name = pol.name
                policy_type = pol.policy_type

        return PolicySimulationResponse(
            allowed=decision.allowed,
            reason=decision.reason,
            matched_policy_id=decision.matched_policy_id,
            matched_policy_name=matched_policy_name,
            policy_type=policy_type,
            policy_version=decision.policy_version,
            matched_role=decision.matched_role,
        )

    async def list_policies(
        self,
        principal: AuthenticatedPrincipal,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[PolicyDefinition]:
        await self.require_permission(principal, "policy:read", tenant_id, session)
        return await self.repository.list_policies(tenant_id, session)

    async def create_policy(
        self,
        principal: AuthenticatedPrincipal,
        data: PolicyCreate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PolicyDefinition:
        self.require_scope(principal, "policy:write")
        await self.require_permission(principal, "policy:write", tenant_id, session)

        if data.cel_expression:
            self.cel_compiler.validate_or_raise(data.cel_expression)

        policy = await self.repository.create_policy(
            data=data,
            tenant_id=tenant_id,
            created_by=principal.user_id,
            session=session,
        )

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type=ExecutionEventType.POLICY_CHANGED.value,
            action="create_policy",
            resource_type="authz_policy",
            resource_id=str(policy.policy_id),
            payload={
                "name": policy.name,
                "effect": policy.effect.value,
                "permissions": policy.permissions,
                "priority": policy.priority,
                "cel_expression": policy.cel_expression,
            },
            session=session,
        )
        return policy

    async def update_policy(
        self,
        principal: AuthenticatedPrincipal,
        policy_id: uuid.UUID,
        data: PolicyUpdate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PolicyDefinition:
        self.require_scope(principal, "policy:write")
        await self.require_permission(principal, "policy:write", tenant_id, session)

        if data.cel_expression:
            self.cel_compiler.validate_or_raise(data.cel_expression)

        policy = await self.repository.update_policy(
            policy_id=policy_id,
            data=data,
            tenant_id=tenant_id,
            session=session,
            updated_by=principal.user_id,
        )

        # Invalidate compiled policy cache
        self.policy_cache.invalidate(tenant_id, policy_id)

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type=ExecutionEventType.POLICY_CHANGED.value,
            action="update_policy",
            resource_type="authz_policy",
            resource_id=str(policy.policy_id),
            payload={
                "name": policy.name,
                "version": policy.version,
                "effect": policy.effect.value,
                "permissions": policy.permissions,
                "priority": policy.priority,
                "cel_expression": policy.cel_expression,
            },
            session=session,
        )
        return policy

    async def delete_policy(
        self,
        principal: AuthenticatedPrincipal,
        policy_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        self.require_scope(principal, "policy:write")
        await self.require_permission(principal, "policy:write", tenant_id, session)
        await self.repository.delete_policy(policy_id, tenant_id, session)

        # Invalidate compiled policy cache
        self.policy_cache.invalidate(tenant_id, policy_id)

        await AuditChainManager.append_event(
            tenant_id=tenant_id,
            user_id=principal.user_id,
            event_type=ExecutionEventType.POLICY_CHANGED.value,
            action="delete_policy",
            resource_type="authz_policy",
            resource_id=str(policy_id),
            payload={"policy_id": str(policy_id)},
            session=session,
        )

    async def list_policy_versions(
        self,
        principal: AuthenticatedPrincipal,
        policy_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[PolicyVersion]:
        """List historical policy versions enforcing policy:read permission."""
        await self.require_permission(principal, "policy:read", tenant_id, session)
        return await self.repository.list_policy_versions(policy_id, tenant_id, session)

    async def get_policy_version(
        self,
        principal: AuthenticatedPrincipal,
        policy_id: uuid.UUID,
        version: str,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PolicyVersion:
        """Fetch a specific historical policy version."""
        await self.require_permission(principal, "policy:read", tenant_id, session)
        ver = await self.repository.get_policy_version(policy_id, version, tenant_id, session)
        if not ver:
            raise AegisNotFoundError(
                f"Policy version '{version}' not found for policy '{policy_id}'."
            )
        return ver
