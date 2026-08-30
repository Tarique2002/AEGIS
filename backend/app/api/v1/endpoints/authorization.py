"""Dynamic RBAC, Role Assignment, and Policy Management REST API Endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_principal
from app.authz.permissions import ALL_PERMISSIONS
from app.authz.schemas import (
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
    RoleUpdate,
    UserRoleAssignment,
    UserRoleAssignmentCreate,
)
from app.authz.service import AuthorizationService
from app.core.auth import AuthenticatedPrincipal
from app.core.errors import AegisNotFoundError
from app.db.session import get_db_session

router = APIRouter(tags=["authorization"])


def get_authz_service() -> AuthorizationService:
    return AuthorizationService()


# ==============================================================================
# Effective Context
# ==============================================================================


@router.get(
    "/authorization/me",
    response_model=EffectiveAuthorizationResponse,
    summary="Get effective authorization context for authenticated caller",
)
async def get_my_authorization(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> EffectiveAuthorizationResponse:
    return await service.get_effective_authorization(
        principal=principal,
        tenant_id=principal.user_id,
        session=session,
    )


# ==============================================================================
# Permissions
# ==============================================================================


@router.get(
    "/permissions",
    response_model=list[str],
    summary="List all canonical system permissions",
)
async def list_permissions(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
) -> list[str]:
    return sorted(ALL_PERMISSIONS)


# ==============================================================================
# Roles
# ==============================================================================


@router.get(
    "/roles",
    response_model=list[Role],
    summary="List all available roles for the tenant",
)
async def list_roles(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> list[Role]:
    return await service.list_roles(
        principal=principal,
        tenant_id=principal.user_id,
        session=session,
    )


@router.post(
    "/roles",
    response_model=Role,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom role for the tenant",
)
async def create_role(
    payload: RoleCreate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> Role:
    return await service.create_role(
        principal=principal,
        data=payload,
        tenant_id=principal.user_id,
        session=session,
    )


@router.get(
    "/roles/{role_id}",
    response_model=Role,
    summary="Fetch role details by ID",
)
async def get_role(
    role_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> Role:
    await service.require_permission(principal, "role:read", principal.user_id, session)
    role = await service.repository.get_role(role_id, principal.user_id, session)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")
    return role


@router.patch(
    "/roles/{role_id}",
    response_model=Role,
    summary="Modify a custom role",
)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> Role:
    service.require_scope(principal, "policy:write")
    await service.require_permission(principal, "role:manage", principal.user_id, session)
    try:
        return await service.repository.update_role(role_id, payload, principal.user_id, session)
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found."
        ) from None


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom role",
)
async def delete_role(
    role_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> None:
    service.require_scope(principal, "policy:write")
    await service.require_permission(principal, "role:manage", principal.user_id, session)
    try:
        await service.repository.delete_role(role_id, principal.user_id, session)
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found."
        ) from None


# ==============================================================================
# Role Assignments
# ==============================================================================


@router.get(
    "/role-assignments",
    response_model=list[UserRoleAssignment],
    summary="List all role assignments within the tenant",
)
async def list_role_assignments(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> list[UserRoleAssignment]:
    await service.require_permission(principal, "role:read", principal.user_id, session)
    return await service.repository.list_role_assignments(principal.user_id, session)


@router.post(
    "/role-assignments",
    response_model=UserRoleAssignment,
    status_code=status.HTTP_201_CREATED,
    summary="Assign role to a user within tenant boundary",
)
async def create_role_assignment(
    payload: UserRoleAssignmentCreate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> UserRoleAssignment:
    return await service.create_role_assignment(
        principal=principal,
        data=payload,
        tenant_id=principal.user_id,
        session=session,
    )


@router.delete(
    "/role-assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a role assignment",
)
async def delete_role_assignment(
    assignment_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> None:
    try:
        await service.delete_role_assignment(
            principal=principal,
            assignment_id=assignment_id,
            tenant_id=principal.user_id,
            session=session,
        )
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role assignment not found."
        ) from None


# ==============================================================================
# Dynamic Policies, Validation, Simulation & Versioning
# ==============================================================================


@router.post(
    "/policies/validate",
    response_model=PolicyValidationResponse,
    summary="Validate a policy expression or rule without saving",
)
async def validate_policy(
    payload: PolicyValidationRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    service: AuthorizationService = Depends(get_authz_service),
) -> PolicyValidationResponse:
    service.require_scope(principal, "policy:read")
    return service.validate_policy(payload)


@router.post(
    "/policies/simulate",
    response_model=PolicySimulationResponse,
    summary="Simulate policy evaluation on sample context without executing resource action",
)
async def simulate_policy(
    payload: PolicySimulationRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> PolicySimulationResponse:
    return await service.simulate_policy(
        principal=principal,
        request=payload,
        tenant_id=principal.user_id,
        session=session,
    )


@router.get(
    "/policies",
    response_model=list[PolicyDefinition],
    summary="List all dynamic policies for the tenant",
)
async def list_policies(
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> list[PolicyDefinition]:
    return await service.list_policies(
        principal=principal,
        tenant_id=principal.user_id,
        session=session,
    )


@router.post(
    "/policies",
    response_model=PolicyDefinition,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new dynamic policy rule",
)
async def create_policy(
    payload: PolicyCreate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> PolicyDefinition:
    return await service.create_policy(
        principal=principal,
        data=payload,
        tenant_id=principal.user_id,
        session=session,
    )


@router.get(
    "/policies/{policy_id}",
    response_model=PolicyDefinition,
    summary="Fetch policy rule details by ID",
)
async def get_policy(
    policy_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> PolicyDefinition:
    await service.require_permission(principal, "policy:read", principal.user_id, session)
    policy = await service.repository.get_policy(policy_id, principal.user_id, session)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found.")
    return policy


@router.get(
    "/policies/{policy_id}/versions",
    response_model=list[PolicyVersion],
    summary="List historical version records for a policy",
)
async def list_policy_versions(
    policy_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> list[PolicyVersion]:
    try:
        return await service.list_policy_versions(
            principal=principal,
            policy_id=policy_id,
            tenant_id=principal.user_id,
            session=session,
        )
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found."
        ) from None


@router.get(
    "/policies/{policy_id}/versions/{version}",
    response_model=PolicyVersion,
    summary="Fetch a specific historical policy version",
)
async def get_policy_version(
    policy_id: uuid.UUID,
    version: str,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> PolicyVersion:
    try:
        return await service.get_policy_version(
            principal=principal,
            policy_id=policy_id,
            version=version,
            tenant_id=principal.user_id,
            session=session,
        )
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy version not found."
        ) from None


@router.patch(
    "/policies/{policy_id}",
    response_model=PolicyDefinition,
    summary="Modify a dynamic policy rule",
)
async def update_policy(
    policy_id: uuid.UUID,
    payload: PolicyUpdate,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> PolicyDefinition:
    try:
        return await service.update_policy(
            principal=principal,
            policy_id=policy_id,
            data=payload,
            tenant_id=principal.user_id,
            session=session,
        )
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found."
        ) from None


@router.delete(
    "/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dynamic policy rule",
)
async def delete_policy(
    policy_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user_principal),
    session: AsyncSession = Depends(get_db_session),
    service: AuthorizationService = Depends(get_authz_service),
) -> None:
    try:
        await service.delete_policy(
            principal=principal,
            policy_id=policy_id,
            tenant_id=principal.user_id,
            session=session,
        )
    except AegisNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found."
        ) from None
