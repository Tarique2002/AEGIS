# AEGIS Attribute-Based Access Control (ABAC) Architecture

## 1. Overview
AEGIS Phase 10 introduces dynamic Attribute-Based Access Control (ABAC) integrated with Role-Based Access Control (RBAC) and Google Common Expression Language (CEL).

---

## 2. Authorization Pipeline
The authorization pipeline executes deterministically fail-closed:

```
Request
  ↓
Authentication & JWT Claims Extraction (user_id, tenant_id, roles, scopes)
  ↓
Token Scope Verification (check_scope / require_scope)
  ↓
AuthorizationContext Construction (Subject, Resource, Environment, Request)
  ↓
PolicyEngine Evaluation:
  1. Explicit Security DENY
  2. Tenant Policy DENY
  3. ABAC / CEL Policy DENY
  4. Missing Token Scope
  5. Missing RBAC Permission
  6. Ownership Validation (tenant_id check)
  7. ABAC / CEL Policy ALLOW
  8. RBAC / Assigned Role ALLOW
  9. Default DENY
  ↓
SafetyGate (7-Stage Circuit & Risk Pipeline)
  ↓
Resource Action
  ↓
Audit Event & Cryptographic SHA-256 Hash Chaining
```

---

## 3. Precedence Rules
- **Explicit DENY Always Wins**: An explicit DENY in a tenant or ABAC policy cannot be overridden by an ALLOW or assigned role.
- **SafetyGate is Independent**: Even if RBAC and ABAC ALLOW an action, SafetyGate verifies risk levels, capability limits, rate limits, and approval requirements.
