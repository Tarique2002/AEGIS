# AEGIS Cryptographic Audit Checkpoints & Signing

## 1. Overview
Audit checkpoints provide signed anchors over sequence ranges `[sequence_start, sequence_end]` of append-only audit events.

```
Audit Event (seq=1) → payload_hash → event_hash
                                         ↓
Audit Event (seq=2) → payload_hash → event_hash
                                         ↓
Audit Event (seq=N) → payload_hash → chain_head
                                         ↓
Signed Audit Checkpoint (tenant_id, seq_start, seq_end, chain_head, signature)
```

---

## 2. Signing Providers
- **LocalSigningProvider**: Development and offline offline signing provider using HMAC-SHA256 with constant-time signature verification.
- **KMSSigningProvider**: Cloud KMS provider abstraction supporting AWS KMS, Google Cloud KMS, and Azure Key Vault with automatic offline fallback to LocalSigningProvider.

---

## 3. Verification Process
`AuditCheckpointVerifier` checks:
1. Cryptographic signature validity over `tenant_id:sequence_start:sequence_end:chain_head`.
2. Sequence range existence and boundary alignment in PostgreSQL.
3. Matching event hash for `chain_head` at `sequence_end`.
4. Monotonic hash continuity across the entire audit chain.
