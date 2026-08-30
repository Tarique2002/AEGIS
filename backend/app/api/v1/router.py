"""API v1 Unified Router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_loops,
    audit_chain,
    auth,
    authorization,
    compliance,
    evaluations,
    health,
    memory,
    orchestrations,
    plans,
    safety,
    tasks,
    tools,
)

api_router = APIRouter()

# Attach health probes (also accessible directly at /api/v1/health/live and /api/v1/health/ready)
api_router.include_router(health.router)

# Attach authentication & token management endpoints
api_router.include_router(auth.router)

# Attach dynamic authorization, RBAC, roles, and policy endpoints (Phase 9 subsystem)
api_router.include_router(authorization.router)

# Attach compliance evidence and attestation endpoints (Phase 10 subsystem)
api_router.include_router(compliance.router)

# Attach cryptographic audit chain endpoints (Phase 9 & 10 subsystem)
api_router.include_router(audit_chain.router)

# Attach task endpoints
api_router.include_router(tasks.router)

# Attach tool endpoints (Phase 2 discovery & execution boundary)
api_router.include_router(tools.router)

# Attach memory endpoints (Phase 3 multi-tier memory subsystem)
api_router.include_router(memory.router)

# Attach evaluation & reflection endpoints (Phase 4 subsystem)
api_router.include_router(evaluations.router)

# Attach planner & execution graph endpoints (Phase 5 subsystem)
api_router.include_router(plans.router)

# Attach controlled autonomous agent loop endpoints (Phase 6 subsystem)
api_router.include_router(agent_loops.router)

# Attach multi-agent orchestration & delegation endpoints (Phase 7 subsystem)
api_router.include_router(orchestrations.router)

# Attach safety, risk policies, approvals & audit endpoints (Phase 8 subsystem)
api_router.include_router(safety.router)
