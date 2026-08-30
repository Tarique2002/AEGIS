"""Multi-tenant database repository for roles, role assignments, and dynamic policies."""

import uuid
from datetime import datetime

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.roles import DEFAULT_ROLE_PERMISSIONS
from app.authz.schemas import (
    PolicyCreate,
    PolicyDefinition,
    PolicyEffect,
    PolicyUpdate,
    PolicyVersion,
    Role,
    RoleCreate,
    RoleUpdate,
    UserRoleAssignment,
    UserRoleAssignmentCreate,
)
from app.core.errors import AegisNotFoundError, RoleAssignmentError
from app.db.models.authorization import (
    PolicyDefinitionModel,
    PolicyVersionModel,
    RoleModel,
    UserRoleAssignmentModel,
)
from app.schemas.common import utc_now


class AuthzRepository:
    """Multi-tenant isolated data access for authorization entities."""

    @staticmethod
    def _is_expired(expires_at: datetime | None) -> bool:
        if not expires_at:
            return False
        now = utc_now()
        if expires_at.tzinfo is None:
            return now.replace(tzinfo=None) > expires_at
        return now > expires_at

    # ==========================================================================
    # Role Operations
    # ==========================================================================

    async def get_role(
        self,
        role_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> Role | None:
        """Fetch role by ID accessible to tenant (system role or tenant-owned)."""
        stmt = select(RoleModel).where(
            RoleModel.id == role_id,
            or_(RoleModel.tenant_id == tenant_id, RoleModel.is_system_role.is_(True)),
        )
        res = await session.execute(stmt)
        m = res.scalar_one_or_none()
        return self._to_role(m) if m else None

    async def list_roles(
        self,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[Role]:
        """List all system roles plus tenant-owned custom roles."""
        stmt = (
            select(RoleModel)
            .where(or_(RoleModel.tenant_id == tenant_id, RoleModel.is_system_role.is_(True)))
            .order_by(RoleModel.is_system_role.desc(), RoleModel.name.asc())
        )
        res = await session.execute(stmt)
        models = res.scalars().all()
        return [self._to_role(m) for m in models]

    async def create_role(
        self,
        data: RoleCreate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> Role:
        """Create a custom tenant-scoped role."""
        model = RoleModel(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            permissions=data.permissions,
            tenant_id=tenant_id,
            is_system_role=False,
            enabled=data.enabled,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(model)
        await session.flush()
        return self._to_role(model)

    async def update_role(
        self,
        role_id: uuid.UUID,
        data: RoleUpdate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> Role:
        """Update a tenant-owned custom role. System roles cannot be modified."""
        stmt = select(RoleModel).where(
            RoleModel.id == role_id,
            RoleModel.tenant_id == tenant_id,
            RoleModel.is_system_role.is_(False),
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Custom role '{role_id}' not found.")

        if data.name is not None:
            model.name = data.name
        if data.description is not None:
            model.description = data.description
        if data.permissions is not None:
            model.permissions = data.permissions
        if data.enabled is not None:
            model.enabled = data.enabled
        model.updated_at = utc_now()
        await session.flush()
        return self._to_role(model)

    async def delete_role(
        self,
        role_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Delete a tenant-owned custom role. System roles cannot be deleted."""
        stmt = select(RoleModel).where(
            RoleModel.id == role_id,
            RoleModel.tenant_id == tenant_id,
            RoleModel.is_system_role.is_(False),
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Custom role '{role_id}' not found.")

        await session.delete(model)
        await session.flush()

    # ==========================================================================
    # Role Assignment Operations
    # ==========================================================================

    async def get_user_effective_roles_and_permissions(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> tuple[list[str], list[str]]:
        """
        Fetch active, non-expired role names and accumulated permissions for a user.
        Always includes the default USER system role permissions.
        """
        stmt = (
            select(UserRoleAssignmentModel)
            .join(RoleModel, UserRoleAssignmentModel.role_id == RoleModel.id)
            .where(
                UserRoleAssignmentModel.user_id == user_id,
                UserRoleAssignmentModel.tenant_id == tenant_id,
                UserRoleAssignmentModel.enabled.is_(True),
                RoleModel.enabled.is_(True),
            )
        )
        res = await session.execute(stmt)
        assignments = res.scalars().all()

        roles_set: set[str] = {"USER"}
        permissions_set: set[str] = set(DEFAULT_ROLE_PERMISSIONS.get("USER", []))

        for a in assignments:
            if not self._is_expired(a.expires_at) and a.role:
                roles_set.add(a.role.name)
                # Add role's permissions
                if a.role.is_system_role and a.role.name in DEFAULT_ROLE_PERMISSIONS:
                    permissions_set.update(DEFAULT_ROLE_PERMISSIONS[a.role.name])
                else:
                    permissions_set.update(a.role.permissions)

        return list(roles_set), list(permissions_set)

    async def create_role_assignment(
        self,
        data: UserRoleAssignmentCreate,
        tenant_id: uuid.UUID,
        assigned_by: uuid.UUID,
        session: AsyncSession,
    ) -> UserRoleAssignment:
        """Assign role to user within tenant boundary. Prevents self-escalation."""
        if data.user_id == assigned_by:
            raise RoleAssignmentError("Users cannot assign or elevate roles to themselves.")

        # Ensure role exists and is accessible
        role = await self.get_role(data.role_id, tenant_id, session)
        if not role:
            raise AegisNotFoundError(f"Role '{data.role_id}' not found.")

        model = UserRoleAssignmentModel(
            id=uuid.uuid4(),
            user_id=data.user_id,
            role_id=data.role_id,
            tenant_id=tenant_id,
            assigned_by=assigned_by,
            expires_at=data.expires_at,
            enabled=data.enabled,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(model)
        await session.flush()
        return self._to_assignment(model)

    async def delete_role_assignment(
        self,
        assignment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Remove a role assignment within tenant boundary."""
        stmt = select(UserRoleAssignmentModel).where(
            UserRoleAssignmentModel.id == assignment_id,
            UserRoleAssignmentModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Role assignment '{assignment_id}' not found.")

        await session.delete(model)
        await session.flush()

    async def list_role_assignments(
        self,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[UserRoleAssignment]:
        """List all role assignments within the tenant."""
        stmt = (
            select(UserRoleAssignmentModel)
            .where(UserRoleAssignmentModel.tenant_id == tenant_id)
            .order_by(desc(UserRoleAssignmentModel.created_at))
        )
        res = await session.execute(stmt)
        return [self._to_assignment(m) for m in res.scalars().all()]

    # ==========================================================================
    # Dynamic Policy Operations
    # ==========================================================================

    async def list_policies(
        self,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[PolicyDefinition]:
        """List all dynamic authorization policies for tenant."""
        stmt = (
            select(PolicyDefinitionModel)
            .where(PolicyDefinitionModel.tenant_id == tenant_id)
            .order_by(PolicyDefinitionModel.priority.asc())
        )
        res = await session.execute(stmt)
        return [self._to_policy(m) for m in res.scalars().all()]

    async def get_policy(
        self,
        policy_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PolicyDefinition | None:
        """Fetch policy by ID enforcing tenant isolation."""
        stmt = select(PolicyDefinitionModel).where(
            PolicyDefinitionModel.id == policy_id,
            PolicyDefinitionModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        m = res.scalar_one_or_none()
        return self._to_policy(m) if m else None

    async def create_policy(
        self,
        data: PolicyCreate,
        tenant_id: uuid.UUID,
        created_by: uuid.UUID,
        session: AsyncSession,
    ) -> PolicyDefinition:
        """Create a new dynamic policy rule for tenant and record version 1.0.0."""
        pol_id = uuid.uuid4()
        model = PolicyDefinitionModel(
            id=pol_id,
            name=data.name,
            version="1.0.0",
            description=data.description,
            tenant_id=tenant_id,
            enabled=data.enabled,
            priority=data.priority,
            effect=data.effect.value,
            policy_type=data.policy_type,
            permissions=data.permissions,
            conditions=data.conditions,
            cel_expression=data.cel_expression,
            created_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(model)

        # Record initial immutable version in history
        version_model = PolicyVersionModel(
            id=uuid.uuid4(),
            policy_id=pol_id,
            tenant_id=tenant_id,
            version="1.0.0",
            name=data.name,
            policy_type=data.policy_type,
            effect=data.effect.value,
            priority=data.priority,
            permissions=data.permissions,
            conditions=data.conditions,
            cel_expression=data.cel_expression,
            change_reason="Initial creation",
            created_by=created_by,
            created_at=utc_now(),
        )
        session.add(version_model)

        await session.flush()
        return self._to_policy(model)

    async def update_policy(
        self,
        policy_id: uuid.UUID,
        data: PolicyUpdate,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        updated_by: uuid.UUID | None = None,
    ) -> PolicyDefinition:
        """Update a dynamic policy, bumping its version and recording immutable history."""
        stmt = select(PolicyDefinitionModel).where(
            PolicyDefinitionModel.id == policy_id,
            PolicyDefinitionModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Policy '{policy_id}' not found.")

        if data.name is not None:
            model.name = data.name
        if data.description is not None:
            model.description = data.description
        if data.priority is not None:
            model.priority = data.priority
        if data.effect is not None:
            model.effect = data.effect.value
        if data.policy_type is not None:
            model.policy_type = data.policy_type
        if data.permissions is not None:
            model.permissions = data.permissions
        if data.conditions is not None:
            model.conditions = data.conditions
        if data.cel_expression is not None:
            model.cel_expression = data.cel_expression
        if data.enabled is not None:
            model.enabled = data.enabled

        # Version increment
        try:
            parts = model.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            model.version = ".".join(parts)
        except Exception:
            model.version = "1.0.1"

        model.updated_at = utc_now()

        # Record immutable version in history
        version_model = PolicyVersionModel(
            id=uuid.uuid4(),
            policy_id=model.id,
            tenant_id=tenant_id,
            version=model.version,
            name=model.name,
            policy_type=model.policy_type,
            effect=model.effect,
            priority=model.priority,
            permissions=model.permissions,
            conditions=model.conditions,
            cel_expression=model.cel_expression,
            change_reason=data.change_reason or "Policy updated",
            created_by=updated_by,
            created_at=utc_now(),
        )
        session.add(version_model)

        await session.flush()
        return self._to_policy(model)

    async def delete_policy(
        self,
        policy_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Delete a dynamic policy rule."""
        stmt = select(PolicyDefinitionModel).where(
            PolicyDefinitionModel.id == policy_id,
            PolicyDefinitionModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Policy '{policy_id}' not found.")

        await session.delete(model)
        await session.flush()

    async def list_policy_versions(
        self,
        policy_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[PolicyVersion]:
        """List all immutable historical versions for a policy."""
        # Ensure policy exists and belongs to tenant
        policy = await self.get_policy(policy_id, tenant_id, session)
        if not policy:
            raise AegisNotFoundError(f"Policy '{policy_id}' not found.")

        stmt = (
            select(PolicyVersionModel)
            .where(
                PolicyVersionModel.policy_id == policy_id,
                PolicyVersionModel.tenant_id == tenant_id,
            )
            .order_by(desc(PolicyVersionModel.created_at))
        )
        res = await session.execute(stmt)
        return [self._to_policy_version(m) for m in res.scalars().all()]

    async def get_policy_version(
        self,
        policy_id: uuid.UUID,
        version: str,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> PolicyVersion | None:
        """Fetch specific historical policy version."""
        stmt = select(PolicyVersionModel).where(
            PolicyVersionModel.policy_id == policy_id,
            PolicyVersionModel.version == version,
            PolicyVersionModel.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        m = res.scalar_one_or_none()
        return self._to_policy_version(m) if m else None

    # ==========================================================================
    # Model Mappings
    # ==========================================================================

    @staticmethod
    def _to_role(m: RoleModel) -> Role:
        return Role(
            role_id=m.id,
            name=m.name,
            description=m.description,
            permissions=m.permissions or [],
            tenant_id=m.tenant_id,
            is_system_role=m.is_system_role,
            enabled=m.enabled,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _to_assignment(m: UserRoleAssignmentModel) -> UserRoleAssignment:
        return UserRoleAssignment(
            assignment_id=m.id,
            user_id=m.user_id,
            role_id=m.role_id,
            tenant_id=m.tenant_id,
            assigned_by=m.assigned_by,
            expires_at=m.expires_at,
            enabled=m.enabled,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _to_policy(m: PolicyDefinitionModel) -> PolicyDefinition:
        return PolicyDefinition(
            policy_id=m.id,
            name=m.name,
            version=m.version,
            description=m.description,
            tenant_id=m.tenant_id,
            enabled=m.enabled,
            priority=m.priority,
            effect=PolicyEffect(m.effect),
            policy_type=m.policy_type,
            permissions=m.permissions or [],
            conditions=m.conditions or {},
            cel_expression=m.cel_expression,
            created_by=m.created_by,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _to_policy_version(m: PolicyVersionModel) -> PolicyVersion:
        return PolicyVersion(
            version_id=m.id,
            policy_id=m.policy_id,
            tenant_id=m.tenant_id,
            version=m.version,
            name=m.name,
            policy_type=m.policy_type,
            effect=PolicyEffect(m.effect),
            priority=m.priority,
            permissions=m.permissions or [],
            conditions=m.conditions or {},
            cel_expression=m.cel_expression,
            change_reason=m.change_reason,
            created_by=m.created_by,
            created_at=m.created_at,
        )
