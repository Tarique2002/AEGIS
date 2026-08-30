"""Dynamic Authorization, RBAC, Token Scopes & Policy Engine module for Phase 9."""

from app.authz.evaluator import AuthorizationEvaluator
from app.authz.permissions import ALL_PERMISSIONS, Permission, is_permission_matching
from app.authz.policy import PolicyEngine
from app.authz.repository import AuthzRepository
from app.authz.roles import DEFAULT_ROLE_PERMISSIONS, SystemRole
from app.authz.schemas import (
    AuthorizationDecision,
    EffectiveAuthorizationResponse,
    PolicyCreate,
    PolicyDefinition,
    PolicyEffect,
    PolicyUpdate,
    Role,
    RoleCreate,
    RoleUpdate,
    TokenScope,
    UserRoleAssignment,
    UserRoleAssignmentCreate,
)
from app.authz.service import AuthorizationService

__all__ = [
    "Permission",
    "ALL_PERMISSIONS",
    "is_permission_matching",
    "SystemRole",
    "DEFAULT_ROLE_PERMISSIONS",
    "TokenScope",
    "PolicyEffect",
    "Role",
    "RoleCreate",
    "RoleUpdate",
    "UserRoleAssignment",
    "UserRoleAssignmentCreate",
    "PolicyDefinition",
    "PolicyCreate",
    "PolicyUpdate",
    "AuthorizationDecision",
    "EffectiveAuthorizationResponse",
    "PolicyEngine",
    "AuthzRepository",
    "AuthorizationEvaluator",
    "AuthorizationService",
]
