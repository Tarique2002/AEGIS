"""AuthorizationContext unifying Subject, Resource, Environment, and Request attributes."""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.authz.abac.attributes import (
    EnvironmentAttributes,
    RequestAttributes,
    ResourceAttributes,
    SubjectAttributes,
)
from app.core.auth import AuthenticatedPrincipal


class AuthorizationContext(BaseModel):
    """
    Unified context for dynamic RBAC, ABAC, and CEL evaluations.
    Populated strictly from verified principal identity, trusted DB resource state, and environment.
    """

    subject: SubjectAttributes
    resource: ResourceAttributes
    environment: EnvironmentAttributes = Field(default_factory=EnvironmentAttributes)
    request: RequestAttributes
    token: dict[str, Any] = Field(default_factory=dict)
    action: str
    tenant_id: uuid.UUID
    resource_type: str
    resource_id: str | None = None

    def to_eval_dict(self) -> dict[str, Any]:
        """Convert context to dictionary representation for CEL evaluation."""
        return {
            "subject": self.subject.model_dump(),
            "resource": self.resource.model_dump(),
            "environment": self.environment.model_dump(),
            "request": self.request.model_dump(),
            "action": self.action,
            "token": self.token,
        }

    @classmethod
    def build(
        cls,
        principal: AuthenticatedPrincipal,
        action: str,
        tenant_id: uuid.UUID,
        resource_type: str,
        resource_id: str | None = None,
        resource_owner_id: str | None = None,
        resource_sensitivity: str = "internal",
        resource_risk_level: str = "LOW",
        effective_roles: list[str] | None = None,
        effective_permissions: list[str] | None = None,
        request_params: dict[str, Any] | None = None,
    ) -> "AuthorizationContext":
        """
        Factory helper creating a validated AuthorizationContext from trusted application state.
        """
        subj = SubjectAttributes(
            user_id=str(principal.user_id),
            tenant_id=str(tenant_id),
            roles=effective_roles or principal.roles,
            permissions=effective_permissions or [],
            scopes=principal.scopes,
            email=principal.email,
            authentication_scheme=principal.auth_scheme,
            is_authenticated=principal.is_authenticated,
        )

        res = ResourceAttributes(
            owner_id=resource_owner_id or str(principal.user_id),
            tenant_id=str(tenant_id),
            resource_type=resource_type,
            resource_id=resource_id,
            sensitivity=resource_sensitivity,
            risk_level=resource_risk_level,
        )

        req = RequestAttributes(
            action=action,
            parameters=request_params or {},
        )

        tok = {
            "sub": str(principal.user_id),
            "scopes": principal.scopes,
            "roles": principal.roles,
            "jti": principal.token_id,
        }

        return cls(
            subject=subj,
            resource=res,
            environment=EnvironmentAttributes(),
            request=req,
            token=tok,
            action=action,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
