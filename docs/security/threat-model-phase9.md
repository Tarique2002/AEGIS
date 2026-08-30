# AEGIS Phase 9 Threat Model & Security Analysis

## 1. Threat Scenarios & Mitigations

### A. Privilege Escalation via Self-Role Assignment
- **Threat**: Authenticated user attempts `POST /api/v1/role-assignments` to assign themselves the `ADMIN` role.
- **Mitigation**:
  - `AuthzRepository.create_role_assignment` explicitly rejects `data.user_id == assigned_by`.
  - Endpoint enforces `require_scope(principal, "policy:write")` and `require_permission(principal, "role:manage")`.

### B. Confused Deputy & Cross-Tenant Policy Escape
- **Threat**: User A attempts to view or modify User B's policy or audit chain by guessing UUIDs.
- **Mitigation**:
  - All SQL queries enforce `WHERE tenant_id = :authenticated_user_id`.
  - Non-existent or cross-tenant records return `404 Not Found`, giving zero leakage of foreign resource existence.

### C. Header-Based Scope & Identity Spoofing
- **Threat**: Untrusted client supplies `X-Scopes: admin` or `X-User-Role: ADMIN` in request headers.
- **Mitigation**:
  - Request headers are completely ignored for authorization.
  - Principal context is extracted exclusively from cryptographically verified HMAC-SHA256 JWT tokens.

### D. Administrative Safety Gate Bypass
- **Threat**: User with `ADMIN` role or `admin:*` permission attempts a critical/forbidden operation (e.g. `shell`, `exec`, `os_system`).
- **Mitigation**:
  - Authorization and Safety are decoupled.
  - `SafetyGate` evaluates after RBAC/Scope checks and strictly denies `RiskCategory.CODE_EXECUTION`, `SYSTEM_OPERATION`, and forbidden capabilities regardless of caller role.

### E. Audit Record Tampering & Deletion
- **Threat**: Malicious actor modifies a stored audit row or deletes an incriminating event.
- **Mitigation**:
  - Append-only `security_audit_chains` table with unique constraint on `(tenant_id, sequence_number)`.
  - `AuditChainVerifier` recomputes SHA-256 payload and chain hashes, flagging payload modifications, sequence gaps, and broken hash links.
