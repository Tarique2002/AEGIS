"""Strongly typed attribute models for ABAC and CEL policy evaluations."""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import utc_now


class SubjectAttributes(BaseModel):
    """Verified identity attributes representing the authenticated actor."""

    user_id: str
    tenant_id: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    email: str | None = None
    authentication_scheme: str = "bearer"
    is_authenticated: bool = True


class ResourceAttributes(BaseModel):
    """Resource metadata and classification attributes."""

    owner_id: str | None = None
    tenant_id: str
    resource_type: str
    resource_id: str | None = None
    resource_status: str = "active"
    sensitivity: str = "internal"
    risk_level: str = "LOW"
    classification: str = "standard"
    created_at: str | None = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)


class EnvironmentAttributes(BaseModel):
    """Environmental and contextual runtime attributes."""

    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())
    environment: str = "production"
    request_id: str | None = None
    authentication_scheme: str = "bearer"


class RequestAttributes(BaseModel):
    """Request-specific parameters and metadata."""

    action: str
    method: str = "POST"
    path: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
