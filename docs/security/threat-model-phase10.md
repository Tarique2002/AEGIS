# AEGIS Phase 10 Threat Model & Security Controls

## 1. System Scope & Trust Boundaries
Phase 10 extends the AEGIS platform with Attribute-Based Access Control (ABAC), Google Common Expression Language (CEL) policy compilation and evaluation, deterministic multi-standard compliance reporting (SOC2/HIPAA), and cryptographically signed audit checkpoints.

### Trust Boundaries
1. **API Client Boundary**: All incoming requests present Bearer JWT tokens. Identity claims (`user_id`, `tenant_id`, `roles`, `scopes`) are verified cryptographically and cannot be spoofed via HTTP headers (`X-Tenant-Id`, `X-Scopes`).
2. **CEL Execution Boundary**: CEL expressions evaluate exclusively against sanitized `AuthorizationContext` in an isolated AST interpreter. Python runtime builtins, OS system calls, database drivers, and network sockets are inaccessible.
3. **Multi-Tenant Database Boundary**: All SQL queries enforce `WHERE tenant_id = :authenticated_user_id`. Cross-tenant lookups strictly return `404 Not Found`.
4. **SafetyGate Independence**: SafetyGate remains the final authority; administrative status (`ADMIN`) or permissive ABAC/CEL rules cannot bypass safety policies, capability gates, budgets, or rate limits.
5. **Cryptographic Checkpoint Boundary**: Signed checkpoints encapsulate append-only sequence ranges `[sequence_start, sequence_end]` with SHA-256 chain heads signed by `LocalSigningProvider` or `KMSSigningProvider`.

---

## 2. Threat Analysis Matrix

| Threat ID | Threat Name | Attack Surface | Mitigation Strategy | Detection Mechanism | Test Coverage | Residual Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **THREAT-10-01** | ABAC Attribute Injection | Client request attributes and headers | Only trusted database state and verified JWT claims populate `SubjectAttributes` and `ResourceAttributes`. Headers like `X-Scopes` or `X-User-Id` are ignored. | Schema validation & `AuthorizationContext.build()` | `test_abac_context.py`, `test_phase10_multitenant_security.py` | Minimal (client-supplied attributes strictly quarantined in `request.parameters`) |
| **THREAT-10-02** | CEL Sandbox Escape | Malicious CEL policy expressions | Restrict CEL AST environment (`ALLOWED_TOP_LEVEL_VARS`). Reject forbidden patterns (`__dunder__`, `import`, `exec`, `eval`, `subprocess`, `os`). | `CELCompiler` security scan & type check | `test_cel_security.py`, `test_cel_compiler.py` | Negligible (safe pure-AST evaluator) |
| **THREAT-10-03** | Privilege Escalation via Policy Mutation | Custom policy creation / modification | Enforces `policy:write` scope and `policy:write` permission. Prevents self-escalation. Validates expressions before activation. | Policy compiler validation & audit event emission | `test_abac_api.py`, `test_policy_simulation.py` | Low |
| **THREAT-10-04** | Cache Poisoning in Policy Cache | Cross-tenant compiled policy reuse | `CompiledPolicyCache` keys compiled ASTs strictly by `(tenant_id, policy_id, policy_version)`. Invalidation on policy update/delete. | Tenant-isolated cache lookups | `test_policy_cache.py` | None |
| **THREAT-10-05** | Audit Checkpoint Forgery | Modified sequence range or chain head | Cryptographically signs `tenant_id:sequence_start:sequence_end:chain_head` using HMAC-SHA256 or RSA. Re-verifies signature and DB event hash chain. | `AuditCheckpointVerifier` | `test_audit_checkpoint.py`, `test_checkpoint_api.py` | Negligible (requires private key) |
| **THREAT-10-06** | Audit Deletion / Tampering | Database direct manipulation | Monotonic sequence validation and SHA-256 hash continuity (`previous_hash == previous.event_hash`) detect gaps and modifications immediately. | `AuditChainVerifier.verify_tenant_chain` | `test_audit_verifier.py`, `test_compliance_api.py` | None (tampering breaks chain) |
| **THREAT-10-07** | Compliance Evidence Fabrication | Fabricated evidence items in reports | Evidence generator queries real audit records in `security_audit_chains` and hashes source events deterministically. | `EvidenceCollector` hash verification | `test_compliance_evidence.py`, `test_compliance_reports.py` | Low |
| **THREAT-10-08** | Credential Leakage in Reports | Compliance JSON/CSV exports | Automated recursive secret redaction scrubs API keys, bearer tokens, JWT secrets, and passwords from export outputs. | `ComplianceExporter` scrubbing filters | `test_compliance_api.py` | Minimal |
