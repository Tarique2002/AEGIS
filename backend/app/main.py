"""FastAPI application entrypoint for AEGIS."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db.qdrant import close_qdrant
from app.db.redis import close_redis

logger = get_logger("aegis.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown routines."""
    # Startup
    setup_logging()
    msg = (
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} "
        f"in [{settings.ENVIRONMENT.value}] mode"
    )
    logger.info(msg)
    yield
    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}...")
    await close_redis()
    await close_qdrant()
    logger.info("Shutdown completed cleanly.")


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    description = (
        "Enterprise-grade autonomous AI agent platform with multi-layer memory, "
        "hybrid retrieval, and self-learning capabilities."
    )
    app = FastAPI(
        title=f"{settings.APP_NAME} — Autonomous AI Agent Platform",
        description=description,
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Security Headers and Request Size Limit Middleware
    @app.middleware("http")
    async def security_middleware(request, call_next):
        # 1. Payload size check
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.REQUEST_MAX_BYTES:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "type": "PayloadTooLargeError",
                                "message": (
                                    "Request payload exceeds maximum allowed size of "
                                    f"{settings.REQUEST_MAX_BYTES} bytes."
                                ),
                                "details": {"max_bytes": settings.REQUEST_MAX_BYTES},
                            }
                        },
                    )
            except ValueError:
                pass

        response = await call_next(request)

        # 2. Production Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Global Exception Handlers
    register_exception_handlers(app)

    # Mount Root Health Endpoints (GET /health/live and GET /health/ready)
    app.include_router(health_router)

    # Mount API v1 Routes
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
