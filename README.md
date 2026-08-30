# AEGIS — Agent Execution, Governance, Intelligence & Safety Platform

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0-red.svg)](https://www.sqlalchemy.org/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://docs.pydantic.dev/)
[![Tests](https://img.shields.io/badge/tests-340%20passed-brightgreen.svg)]()
[![Type Checked](https://img.shields.io/badge/mypy-passed-blue.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-ruff-black.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AEGIS** is an enterprise-grade, multi-tenant autonomous AI agent platform engineered for robust task execution, multi-layered memory, dynamic DAG planning, multi-agent orchestration, multi-factor safety gating, dynamic RBAC/ABAC authorization with Google Common Expression Language (CEL), SOC2/HIPAA compliance attestation, and cryptographically chained audit logging.

---

## 1. High-Level Architecture

```
                                    +-----------------------------------------+
                                    |         Client / API Consumers          |
                                    +-----------------------------------------+
                                                         │
                                                         ▼
                                    +-----------------------------------------+
                                    |     JWT Authentication & Scope Check    |
                                    +-----------------------------------------+
                                                         │
                                                         ▼
                                    +-----------------------------------------+
                                    |     Dynamic RBAC + ABAC (CEL) Engine    |
                                    +-----------------------------------------+
                                                         │
                                                         ▼
                                    +-----------------------------------------+
                                    |    SafetyGate 7-Stage Risk Assessment   |
                                    +-----------------------------------------+
                                                         │
                                                         ▼
                         ┌───────────────────────────────┴───────────────────────────────┐
                         ▼                                                               ▼
        +---------------------------------+                             +---------------------------------+
        |     Orchestrator & Workers      |                             |   Autonomous Loop Controller    |
        |  (Delegation, Sub-tasks, Budget)|                             |  (Observe -> Plan -> Execute -> |
        +---------------------------------+                             |   Evaluate -> Reflect -> Decide)|
                         │                                              +---------------------------------+
                         └───────────────────────────────┬───────────────────────────────┘
                                                         │
                                                         ▼
                                    +-----------------------------------------+
                                    |     DAG Execution Graph & Checkpoints   |
                                    +-----------------------------------------+
                                                         │
                                ┌────────────────────────┴────────────────────────┐
                                ▼                                                 ▼
               +---------------------------------+               +---------------------------------+
               |     Tool Execution Engine       |               |     Multi-Layer Memory Engine   |
               | (AST Sandbox, Timeout, Policy)  |               | (Working, Episodic, Semantic)   |
               +---------------------------------+               +---------------------------------+
                                │                                                 │
                                └────────────────────────┬────────────────────────┘
                                                         │
                                                         ▼
                                    +-----------------------------------------+
                                    |     Cryptographic SHA-256 Audit Chain   |
                                    |   (Append-Only, Signed Checkpoints)     |
                                    +-----------------------------------------+
                                                         │
                                                         ▼
                                    +-----------------------------------------+
                                    |     Compliance Evidence & Attestation   |
                                    |      (SOC2, HIPAA, Reproducible)        |
                                    +-----------------------------------------+
```

---

## 2. Core Capabilities & Implemented Phases

* **Phase 0 — Foundation & Infrastructure**: Asynchronous PostgreSQL (`asyncpg`), Redis, Qdrant vector database, health check probes (`/api/v1/health/live`, `/ready`), Pydantic settings.
* **Phase 1 — Stateful Agent Runtime**: Strongly typed `AgentState`, LLM provider abstraction (Ollama, OpenAI, Anthropic, Gemini), structured responses, monotonic event emission, task management.
* **Phase 2 — Secure Tool Execution Engine**: Dependency-injected `ToolRegistry`, AST-safe `CalculatorTool`, `ToolPolicy` gating (`SAFE`, `RESTRICTED`, `DANGEROUS`), async timeout boundaries (`ToolExecutor`), exception isolation.
* **Phase 3 — Multi-Layer Memory Engine**: Redis-backed Working Memory with TTL, PostgreSQL-backed Episodic Memory for run summaries, Qdrant-backed Semantic Memory with cosine vector similarity and 2-stage deduplication, normalized multi-factor retrieval ranking.
* **Phase 4 — Evaluation & Reflection Engine**: Post-run evaluation and diagnostic reflection, normalized weighted multi-factor scoring, safety gate overrides, failure mode taxonomy, evidence-backed root-cause classification.
* **Phase 5 — Dynamic Planner & Execution Graph**: Structured task planning, DAG execution graphs, typed plan nodes (`TOOL`, `LLM`, `TRANSFORM`, `CONDITION`, `FINAL`), topological sorting, Kahn's cycle detection, bounded parallel concurrency, durable checkpoint snapshots.
* **Phase 6 — Controlled Autonomous Agent Loop**: Bounded autonomous control loop (`Observe -> Plan -> Execute -> Evaluate -> Reflect -> Decide`), prompt context isolation (`INSTRUCTION`, `DATA`, `MEMORY`), automated secret redaction, hard resource budgets (`AgentBudget`), multi-factor stagnation detection, safety guardrails.
* **Phase 7 — Multi-Agent Orchestration & Delegation**: Centralized Orchestrator with specialized agent workers (`RESEARCHER`, `CODER`, `ANALYST`, `CRITIC`), bounded task decomposition, capability verification, parallel worker scheduling, aggregated synthesis.
* **Phase 8 — Safety Gates, Risk Policies & Platform Hardening**: 7-stage `SafetyGate` pipeline, capability gating, prompt injection detection, rate limiting, human approval hooks with HMAC tokens, circuit breaker cooldowns.
* **Phase 9 — Dynamic RBAC, Token Scopes & Cryptographic Audit**: Dynamic role and permission management, tenant-isolated role assignments, token scope validation, append-only cryptographic audit chain (`security_audit_chains`) linked via SHA-256 hash chains.
* **Phase 10 — ABAC + CEL + Compliance Evidence + Audit Checkpoints**: Attribute-Based Access Control (ABAC) using sandboxed Google Common Expression Language (CEL), immutable policy versioning, automated evidence extraction for SOC2/HIPAA, deterministic attestation reports with canonical hashes, and signed cryptographic audit checkpoints with offline verification.

---

## 3. Security Architecture & Trust Boundaries

1. **Authentication**: All protected endpoints require cryptographically verified Bearer JWT tokens. Identity claims (`user_id`, `tenant_id`, `roles`, `scopes`) are derived exclusively from verified tokens and trusted database state. Headers like `X-User-Id` or `X-Scopes` cannot be spoofed.
2. **Tenant Isolation**: Every database query enforces multi-tenant boundary isolation (`tenant_id == principal.user_id`). Cross-tenant lookups strictly return `404 Not Found`.
3. **Fail-Closed Authorization (RBAC + ABAC + CEL)**: 9-stage deterministic precedence:
   `Explicit DENY -> Tenant Policy DENY -> ABAC/CEL DENY -> Scope Check -> RBAC Permission -> Ownership Check -> ABAC/CEL ALLOW -> Role ALLOW -> Default DENY`.
4. **SafetyGate Independence**: Administrative privileges (`ADMIN`) or permissive ABAC policies cannot bypass the `SafetyGate` risk assessment, capability boundaries, budgets, or circuit breakers.
5. **Tool Sandboxing**: Strict AST-only execution for calculations, zero dynamic imports (`eval`, `exec`, `subprocess`, `os.system` are strictly forbidden).
6. **Cryptographic Audit Integrity**: Append-only audit records are chained via SHA-256 (`previous_hash`, `payload_hash`, `event_hash`). Periodic audit checkpoints sign sequence ranges `[sequence_start, sequence_end]` with HMAC-SHA256 / RSA.
7. **Secret Redaction**: Automated scrubbing of credentials, bearer tokens, and private keys prior to audit emission and compliance report generation.

---

## 4. API Reference

### Major Subsystems & Endpoints

| Subsystem | Prefix | Description |
| :--- | :--- | :--- |
| **Health** | `/api/v1/health` | Liveness (`/live`) and readiness (`/ready`) probes |
| **Auth & Tokens** | `/api/v1/auth` | User registration, login, JWT token issuance, and revocation |
| **Tasks** | `/api/v1/tasks` | Stateful task lifecycle, step execution, and trace events |
| **Tools** | `/api/v1/tools` | Tool discovery, capability querying, and secure tool execution |
| **Memory** | `/api/v1/memory` | Working, episodic, and semantic memory search and management |
| **Evaluations** | `/api/v1/evaluations` | Automated trace scoring, diagnostic reflections, and criteria |
| **Planner & Graphs** | `/api/v1/plans` | Dynamic task decomposition, DAG graph execution, checkpoints |
| **Agent Loops** | `/api/v1/agent-loops` | Bounded autonomous agent loop sessions and resume controls |
| **Orchestrations** | `/api/v1/orchestrations` | Multi-agent task decomposition, worker delegation, synthesis |
| **Safety & Approvals** | `/api/v1/safety` | Safety audits, approval requests, and circuit breaker status |
| **Authorization & RBAC** | `/api/v1/roles`, `/api/v1/policies` | Roles, permissions, CEL policy simulation, validation, versions |
| **Audit & Checkpoints** | `/api/v1/security/audit` | Cryptographic hash chain verification and signed checkpoints |
| **Compliance** | `/api/v1/compliance` | Controls, evidence items, and SOC2/HIPAA attestation reports |

---

## 5. Local Setup & Quickstart

### Prerequisites
- Python 3.12+
- Docker & Docker Compose (for PostgreSQL, Redis, Qdrant)

### 1. Clone & Environment Setup
```bash
git clone https://github.com/Tarique2002/AEGIS.git
cd AEGIS

# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.venv\Scripts\Activate.ps1
# (Linux/macOS)
# source .venv/bin/activate

# Install dependencies
pip install -e .
```

### 2. Start Infrastructure Services
```bash
docker-compose up -d
```

### 3. Run Database Migrations
```bash
cd backend
alembic upgrade head
cd ..
```

### 4. Start the Application
```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

* **Interactive API Documentation (Swagger)**: `http://localhost:8000/docs`
* **Alternative API Documentation (ReDoc)**: `http://localhost:8000/redoc`

---

## 6. Testing & Quality Verification

All 340 tests across Phases 0 through 10 run completely offline without requiring external paid API keys.

```bash
# 1. Run Complete Pytest Suite
.venv\Scripts\pytest -v backend/tests

# 2. Run Ruff Code Linter
.venv\Scripts\ruff check backend

# 3. Run Ruff Format Verification
.venv\Scripts\ruff format --check backend

# 4. Run MyPy Static Type Analysis
.venv\Scripts\python -m mypy backend/app
```

### Verified Test Results
- **Pytest**: `340 passed in 90.52s` (100% pass rate)
- **Ruff**: `All checks passed!`, `305 files already formatted`
- **MyPy**: `Success: no issues found in 188 source files`

---

## 7. Security Regression Test Matrix

AEGIS includes extensive automated regression test suites covering:
- **Authentication**: JWT forgery rejection, expired token rejection, token revocation list enforcement.
- **Tenant Isolation**: Cross-tenant task, agent-loop, memory vector, orchestration, checkpoint, and audit event isolation.
- **Tool Security**: Dangerous tool blocking, AST calculator sandbox escape attempts, oversized arguments rejection.
- **ABAC/CEL Security**: Dangerous Python pattern rejection (`import`, `eval`, `exec`, `subprocess`, `os`, `__dunder__`), invalid syntax rejection, cross-tenant cache isolation.
- **Audit Integrity**: Hash chain tampering detection, invalid checkpoint signature rejection, sequence gap detection.
- **Safety Gate**: Immutability of SafetyGate against administrative bypass.

---

## 8. License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
