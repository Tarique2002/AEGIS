"""Standard Compliance Control Definitions for SOC2 / HIPAA / ISO27001."""

from app.compliance.schemas import ComplianceControl, ControlStatus
from app.schemas.common import utc_now

STANDARD_CONTROLS: list[ComplianceControl] = [
    ComplianceControl(
        control_id="AUTH-001",
        name="Authenticated Access Required",
        description="All API requests to protected endpoints require valid JWT authentication.",
        category="Authentication",
        evidence_sources=["security_audit_chains", "execution_events"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUTH-002",
        name="Cryptographically Verified Identity",
        description=(
            "Principal identity is cryptographically verified via signature and "
            "token revocation lists."
        ),
        category="Authentication",
        evidence_sources=["security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUTH-003",
        name="Fine-Grained Authorization",
        description=(
            "Dynamic RBAC and ABAC policies enforce least-privilege permission checks "
            "on all actions."
        ),
        category="Authorization",
        evidence_sources=["authz_policies", "security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUTH-004",
        name="Tenant Isolation",
        description=(
            "Multi-tenant isolation enforced strictly at database boundary via "
            "tenant_id constraints."
        ),
        category="Authorization",
        evidence_sources=["authz_policies", "security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUTH-005",
        name="Administrative Activity Auditing",
        description=(
            "All administrative role assignments, policy changes, and permission "
            "modifications are audited."
        ),
        category="Audit",
        evidence_sources=["security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="SEC-001",
        name="SafetyGate Enforcement",
        description=(
            "Potentially hazardous actions pass through 7-stage SafetyGate risk "
            "assessment prior to execution."
        ),
        category="Safety",
        evidence_sources=["safety_audits", "execution_events"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="SEC-002",
        name="Secret Redaction",
        description=(
            "Sensitive credentials, tokens, and keys are automatically scrubbed "
            "prior to audit logging."
        ),
        category="Data Protection",
        evidence_sources=["security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUD-001",
        name="Append-Only Audit Logging",
        description=(
            "Audit events are stored in append-only storage with strict monotonic "
            "sequence numbers."
        ),
        category="Audit",
        evidence_sources=["security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUD-002",
        name="Cryptographic Audit Chaining",
        description=(
            "Audit records are chained via SHA-256 hash links "
            "(previous_hash, payload_hash, event_hash)."
        ),
        category="Audit",
        evidence_sources=["security_audit_chains"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="AUD-003",
        name="Audit Integrity Verification",
        description=(
            "On-demand and automated verification detects payload modification, "
            "sequence gap, or link break."
        ),
        category="Audit",
        evidence_sources=["security_audit_chains", "security_audit_checkpoints"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="POL-001",
        name="Policy Version Tracking",
        description=(
            "Authorization policies maintain immutable version histories capturing " "every change."
        ),
        category="Policy Governance",
        evidence_sources=["authz_policy_versions"],
        status=ControlStatus.COMPLIANT,
    ),
    ComplianceControl(
        control_id="POL-002",
        name="Policy Mutation Auditing",
        description=(
            "All policy creations, modifications, and deletions generate attested " "audit events."
        ),
        category="Policy Governance",
        evidence_sources=["security_audit_chains", "authz_policy_versions"],
        status=ControlStatus.COMPLIANT,
    ),
]


def get_standard_controls() -> list[ComplianceControl]:
    """Return a fresh copy of standard compliance controls."""
    now = utc_now()
    return [c.model_copy(update={"last_verified_at": now}) for c in STANDARD_CONTROLS]
