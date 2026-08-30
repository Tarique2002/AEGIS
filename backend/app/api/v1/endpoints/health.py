"""Health and readiness endpoints for container lifecycle and observability."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.qdrant import check_qdrant_health
from app.db.redis import check_redis_health
from app.db.session import check_database_health

router = APIRouter(tags=["Health & Readiness"])


class LivenessResponse(BaseModel):
    status: str = "live"
    app_name: str
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DependencyStatus(BaseModel):
    database: str
    redis: str
    qdrant: str


class ReadinessResponse(BaseModel):
    status: str  # "ready" | "not_ready"
    dependencies: DependencyStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness Probe",
    description="Confirms that the FastAPI application process is up and accepting requests.",
)
async def liveness() -> LivenessResponse:
    """Liveness probe: verifies process health without external dependencies."""
    return LivenessResponse(
        status="live",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Evaluates connectivity to PostgreSQL, Redis, and Qdrant infrastructure.",
)
async def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe: validates external dependencies concurrently."""
    # Execute checks concurrently with bounded timeouts
    db_result, redis_result, qdrant_result = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        check_qdrant_health(),
        return_exceptions=True,
    )

    db_status = (
        "healthy"
        if isinstance(db_result, dict) and db_result.get("status") == "healthy"
        else "unhealthy"
    )
    redis_status = (
        "healthy"
        if isinstance(redis_result, dict) and redis_result.get("status") == "healthy"
        else "unhealthy"
    )
    qdrant_status = (
        "healthy"
        if isinstance(qdrant_result, dict) and qdrant_result.get("status") == "healthy"
        else "unhealthy"
    )

    all_healthy = (
        db_status == "healthy" and redis_status == "healthy" and qdrant_status == "healthy"
    )

    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_healthy else "not_ready",
        dependencies=DependencyStatus(
            database=db_status,
            redis=redis_status,
            qdrant=qdrant_status,
        ),
    )
