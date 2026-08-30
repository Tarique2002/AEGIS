# AEGIS Safety Gates, Risk Policies & Platform Hardening Architecture (Phase 8)

## 1. Overview & Trust Boundaries
AEGIS enforces a multi-layered, fail-closed security and risk-control boundary. Every consequential action initiated by an agent, worker, tool invocation, orchestration plan, or memory mutation passes through explicit risk assessment, policy validation, authorization, rate limiting, and 7-stage safety gates prior to execution.

```
                  USER OBJECTIVE / API REQUEST
                                │
                                ▼
                      [ Authentication Gate ]
                      (JWT Signature, Expiration, Revocation)
                                │
                                ▼
                     [ Authorization Gate ]
                     (Tenant Ownership, Principal Context)
                                │
                                ▼
                   [ Planner / Orchestrator ]
                                │
                                ▼
                    [ Risk Assessment Engine ]
                    (Blast Radius, Category Matrix)
                                │
                                ▼
                        [ Safety Policy ]
                        (Max Risk, Denied Categories)
                                │
                                ▼
                       [ 7-Stage Safety Gate ]
                       (Auth, Owner, Cap, Risk, Budget, Rate, Policy)
                                │
                                ▼
                        [ Safety Budget Gate ]
                                │
                                ▼
                     [ Capability / Tool Policy ]
                                │
                                ▼
                        [ Safe Execution ]
                                │
                                ▼
                      [ Observation & Trace ]
                                │
                                ▼
                        [ Evaluation Engine ]
                                │
                                ▼
                  [ Append-Only Safety Audit Log ]
```

---

## 2. Risk Model and Taxonomy
Every operation is evaluated against a 5-tier risk taxonomy and 13 functional categories.

### Risk Levels
- `NONE`: Internal non-consequential operations (e.g. status inquiries).
- `LOW`: Deterministic, read-only computations and local state retrieval (e.g. arithmetic, reading approved own memory).
- `MEDIUM`: State-modifying operations within bounded limits (e.g. episodic memory writes).
- `HIGH`: Operations with egress, external side effects, or high resource utilization (e.g. external network communication). Requires explicit human approval.
- `CRITICAL`: Dangerous, potentially destructive, or boundary-breaking operations (e.g. arbitrary code execution, OS commands, database drops). **Strictly DENIED by default**.

### Risk Categories
`READ_ONLY`, `COMPUTATION`, `DATA_ACCESS`, `MEMORY_WRITE`, `EXTERNAL_COMMUNICATION`, `CODE_EXECUTION`, `SYSTEM_OPERATION`, `FINANCIAL`, `AUTHENTICATION`, `PRIVACY`, `SECURITY`, `DESTRUCTIVE`, `UNKNOWN`.

---

## 3. The 7-Stage Safety Gate Pipeline
1. **Authentication Gate**: Validates principal presence and token validity.
2. **Ownership Gate**: Verifies tenant isolation and resource ownership.
3. **Capability Gate**: Ensures requested capabilities conform to authorized limits.
4. **Risk Gate**: Computes blast radius and flags critical operations.
5. **Budget Gate**: Validates cumulative resource consumption.
6. **Rate-Limit Gate**: Evaluates tenant-scoped token buckets / sliding windows via Redis.
7. **Policy Gate**: Enforces category blacklists, payload bounds, and prompt injection filters.

---

## 4. Token Revocation & Identity Integrity
- Access tokens contain unique `jti` identifiers.
- Revocations are persisted to Redis key `aegis:auth:revoked:{jti}` with TTL matching token expiry.
- Verification checks revocation status on every request.
- Users can revoke their own sessions via `POST /api/v1/auth/revoke`. Cross-tenant revocations are forbidden.

---

## 5. Tenant Rate Limiting
- Tenant-scoped Redis keys: `aegis:ratelimit:user:{user_id}:{endpoint_type}`.
- Configurable limits:
  - Auth: 20 req/min
  - General API: 120 req/min
  - Tools: 30 req/min
  - Orchestration: 10 req/min
  - Memory writes: 60 req/min
- Breaches return `429 Too Many Requests` with safe `retry_after_seconds`.

---

## 6. Human-in-the-Loop Approval Workflow
- Consequential actions exceeding the policy risk threshold (e.g., `RiskLevel.MEDIUM`) generate an `ApprovalRequest`.
- Approvals are strictly scoped to `user_id`, `task_id`, `action`, `resource`, and `policy_version`.
- Approvals expire automatically after `APPROVAL_TTL_SECONDS` (default: 300s / 5 minutes).
- Expired or cancelled approvals cannot be executed.

---

## 7. Emergency Stop & Circuit Breaker
- **Emergency Stop Controller**: Freezes tasks, runs, or orchestrations immediately when critical violations or runaway conditions are detected. Resume requires explicit intervention.
- **Safety Circuit Breaker**: Tracks failures across tools, workers, and external services:
  - `CLOSED`: Normal operation.
  - `OPEN`: Trips upon 5 consecutive failures, rejecting calls immediately without cascading load.
  - `HALF_OPEN`: Probes service health after a 60-second cooldown.

---

## 8. Prompt Injection & Secret Redaction
- **Input Trust Model**:
  `SYSTEM` > `AUTHENTICATED_USER` > `TRUSTED_INTERNAL` > `WORKER_OUTPUT` > `MEMORY` > `TOOL_OUTPUT` > `EXTERNAL_CONTENT`.
  Untrusted data (tool outputs, memory, external content) is treated strictly as **DATA**, never as instructions.
- **Secret Redaction**: Automatic scrubbing of API keys, Bearer tokens, passwords, private keys, and database connection strings before logs, events, audit records, or persistence.
