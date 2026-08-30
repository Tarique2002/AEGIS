# AEGIS Compliance Evidence & Attestation

## 1. Overview
The AEGIS compliance engine generates verifiable, reproducible attestation reports for SOC2, HIPAA, and ISO27001 by collecting real evidence directly from cryptographic audit trails (`security_audit_chains`).

---

## 2. Standard Controls
- **AUTH-001**: Authenticated access required
- **AUTH-002**: Cryptographically verified identity
- **AUTH-003**: Fine-grained authorization (RBAC/ABAC)
- **AUTH-004**: Multi-tenant database boundary isolation
- **AUTH-005**: Administrative activity auditing
- **SEC-001**: SafetyGate risk & capability enforcement
- **SEC-002**: Automated secret redaction
- **AUD-001**: Append-only monotonic audit logging
- **AUD-002**: Cryptographic SHA-256 hash chaining
- **AUD-003**: Audit integrity verification & tampering detection
- **POL-001**: Policy version tracking (immutable history)
- **POL-002**: Policy mutation auditing

---

## 3. Evidence & Reproducibility
Every generated report contains:
- `source_hash`: SHA-256 hash over all evaluated audit records in reporting window.
- `report_hash`: Deterministic SHA-256 hash of report parameters, controls, and evidence summary.
- `audit_chain_head`: Current cryptographic head hash of tenant audit chain.
