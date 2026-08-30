"""SQLAlchemy models for Phase 9 Dynamic Authorization, RBAC, and Audit Attestation."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.user import User


class RoleModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Custom and system role definition."""

    __tablename__ = "authz_roles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    assignments: Mapped[list["UserRoleAssignmentModel"]] = relationship(
        "UserRoleAssignmentModel", back_populates="role", cascade="all, delete-orphan"
    )


class UserRoleAssignmentModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tenant-scoped role assignment linking user to role."""

    __tablename__ = "authz_role_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authz_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    role: Mapped["RoleModel"] = relationship(
        "RoleModel", back_populates="assignments", lazy="selectin"
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="selectin")


class PolicyDefinitionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Dynamic tenant authorization policy rule supporting RBAC, ABAC, and CEL expressions."""

    __tablename__ = "authz_policies"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    effect: Mapped[str] = mapped_column(String(20), default="ALLOW", nullable=False)
    policy_type: Mapped[str] = mapped_column(String(20), default="COMBINED", nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cel_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class PolicyVersionModel(Base, UUIDPrimaryKeyMixin):
    """Immutable version history for dynamic tenant policies."""

    __tablename__ = "authz_policy_versions"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authz_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(20), default="COMBINED", nullable=False)
    effect: Mapped[str] = mapped_column(String(20), default="ALLOW", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cel_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class AuditChainModel(Base, UUIDPrimaryKeyMixin):
    """
    Cryptographically attested append-only audit event record.
    Enforces hash chaining with previous_hash, payload_hash, and event_hash.
    """

    __tablename__ = "security_audit_chains"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence_number", name="uq_audit_chain_tenant_seq"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
