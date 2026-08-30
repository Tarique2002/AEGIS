# AEGIS Dynamic Authorization & Audit Attestation Architecture (Phase 9)

## 1. Overview
Phase 9 extends AEGIS with a multi-tenant dynamic authorization system, fine-grained token scopes, deterministic RBAC & policy engines, and a cryptographically attested append-only audit chain using SHA-256 hash chaining.

---

## 2. Authorization Pipeline & Invariants

```
AUTHENTICATION
      ↓
AuthenticatedPrincipal
      ↓
Token Scope Validation (check_scope / require_scope)
      ↓
RBAC / Dynamic Policy Evaluation (PolicyEngine)
      ↓
Ownership Validation (WHERE tenant_id = :user_id)
      ↓
SafetyGate (7-stage pipeline: Capability, Risk, Budget, Rate-limit, Policy)
      ↓
Resource Action
      ↓
Audit Event Emission & Cryptographic Chain (SHA-256 hash chaining)
```

### Key Security Invariants:
1. **Multi-Tenant Isolation**: Tenant data and dynamic policies are strictly isolated by `tenant_id`. Cross-tenant lookups return `404 Not Found`.
2. **Fail-Closed Default**: Actions are `DENY` unless explicitly matched by an `ALLOW` policy rule or granted role permission.
3. **Deterministic Precedence**:
   1. Explicit `DENY` in dynamic tenant policies (highest precedence)
   2. Missing required token scope
   3. Missing permission
   4. Explicit `ALLOW` policy / assigned role permissions
   5. Default `DENY`
4. **SafetyGate Independence**: `ADMIN` or `SECURITY_ADMIN` permissions NEVER bypass Phase 8 SafetyGate.
5. **No Header-based Identity/Scope Trust**: Scopes and roles are read strictly from verified JWT claims.

---

## 3. System Roles & Permissions

| Role | Scope / Purpose | Default Permissions |
| :--- | :--- | :--- |
| **VIEWER** | Read-only inspection | `task:read`, `tool:read`, `memory:read`, `orchestration:read`, `safety:read`, `policy:read`, `user:read`, `role:read` |
| **USER** | Standard agent interactions | `task:*`, `tool:read`, `tool:execute`, `memory:read`, `memory:write`, `orchestration:*`, `safety:read`, `token:revoke` |
| **RESEARCHER** | Research & deep memory | USER permissions + `memory:delete` |
| **OPERATOR** | Operational management | USER permissions + `safety:approve` |
| **SECURITY_ADMIN**| Safety & authorization | `safety:*`, `policy:*`, `role:*`, `user:*`, `token:*`, `memory:read`, `task:read` |
| **ADMIN** | Administrative full access | `admin:*` |

---

## 4. Cryptographic Audit Chain Attestation

Audit records in `security_audit_chains` form a cryptographically linked append-only Merkle-like chain:
- Genesis event: `previous_hash = "0" * 64`
- Canonical JSON payload with secret redaction:
  $$\text{payload\_hash} = \text{SHA256}(\text{canonical}(\text{scrubbed\_payload}))$$
- Event hash chaining:
  $$\text{event\_hash} = \text{SHA256}(\text{canonical}(\text{sequence\_number}, \text{event\_type}, \text{action}, \text{resource}, \text{payload\_hash}, \text{previous\_hash}, \text{policy\_version}))$$
- `AuditChainVerifier` performs on-demand verification of monotonic sequencing, hash linkage, and payload integrity.
