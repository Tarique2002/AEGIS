"""System Roles and default permission mappings for Phase 9."""

from enum import Enum

from app.authz.permissions import Permission


class SystemRole(str, Enum):
    """Secure default system roles for AEGIS platform."""

    VIEWER = "VIEWER"
    USER = "USER"
    RESEARCHER = "RESEARCHER"
    OPERATOR = "OPERATOR"
    SECURITY_ADMIN = "SECURITY_ADMIN"
    ADMIN = "ADMIN"


DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    SystemRole.VIEWER.value: [
        Permission.TASK_READ.value,
        Permission.TOOL_READ.value,
        Permission.MEMORY_READ.value,
        Permission.ORCHESTRATION_READ.value,
        Permission.SAFETY_READ.value,
        Permission.POLICY_READ.value,
        Permission.USER_READ.value,
        Permission.ROLE_READ.value,
    ],
    SystemRole.USER.value: [
        Permission.TASK_READ.value,
        Permission.TASK_CREATE.value,
        Permission.TASK_CANCEL.value,
        Permission.TASK_RESUME.value,
        Permission.TOOL_READ.value,
        Permission.TOOL_EXECUTE.value,
        Permission.MEMORY_READ.value,
        Permission.MEMORY_WRITE.value,
        Permission.ORCHESTRATION_READ.value,
        Permission.ORCHESTRATION_CREATE.value,
        Permission.ORCHESTRATION_CANCEL.value,
        Permission.SAFETY_READ.value,
        Permission.TOKEN_REVOKE.value,
    ],
    SystemRole.RESEARCHER.value: [
        Permission.TASK_READ.value,
        Permission.TASK_CREATE.value,
        Permission.TASK_CANCEL.value,
        Permission.TASK_RESUME.value,
        Permission.TOOL_READ.value,
        Permission.TOOL_EXECUTE.value,
        Permission.MEMORY_READ.value,
        Permission.MEMORY_WRITE.value,
        Permission.MEMORY_DELETE.value,
        Permission.ORCHESTRATION_READ.value,
        Permission.ORCHESTRATION_CREATE.value,
        Permission.ORCHESTRATION_CANCEL.value,
        Permission.SAFETY_READ.value,
        Permission.TOKEN_REVOKE.value,
    ],
    SystemRole.OPERATOR.value: [
        Permission.TASK_READ.value,
        Permission.TASK_CREATE.value,
        Permission.TASK_CANCEL.value,
        Permission.TASK_RESUME.value,
        Permission.TOOL_READ.value,
        Permission.TOOL_EXECUTE.value,
        Permission.MEMORY_READ.value,
        Permission.MEMORY_WRITE.value,
        Permission.ORCHESTRATION_READ.value,
        Permission.ORCHESTRATION_CREATE.value,
        Permission.ORCHESTRATION_CANCEL.value,
        Permission.SAFETY_READ.value,
        Permission.SAFETY_APPROVE.value,
        Permission.TOKEN_REVOKE.value,
    ],
    SystemRole.SECURITY_ADMIN.value: [
        Permission.SAFETY_READ.value,
        Permission.SAFETY_APPROVE.value,
        Permission.SAFETY_AUDIT.value,
        Permission.POLICY_READ.value,
        Permission.POLICY_WRITE.value,
        Permission.USER_READ.value,
        Permission.USER_MANAGE.value,
        Permission.ROLE_READ.value,
        Permission.ROLE_MANAGE.value,
        Permission.TOKEN_REVOKE.value,
        Permission.TASK_READ.value,
        Permission.ORCHESTRATION_READ.value,
        Permission.MEMORY_READ.value,
    ],
    SystemRole.ADMIN.value: [
        Permission.ADMIN_ALL.value,
    ],
}
