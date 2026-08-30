"""Qdrant client abstraction and readiness probe."""

import logging

from qdrant_client import AsyncQdrantClient

from app.core.config import settings

logger = logging.getLogger("aegis.qdrant")

_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Get or initialize the asynchronous Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        if settings.QDRANT_API_KEY:
            _qdrant_client = AsyncQdrantClient(
                url=settings.qdrant_connection_url,
                api_key=settings.QDRANT_API_KEY,
                timeout=settings.QDRANT_TIMEOUT_SECONDS,
            )
        else:
            _qdrant_client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                grpc_port=settings.QDRANT_GRPC_PORT,
                timeout=settings.QDRANT_TIMEOUT_SECONDS,
            )
    return _qdrant_client


async def close_qdrant() -> None:
    """Close the Qdrant client connection on application shutdown."""
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
        logger.info("Closed Qdrant client connection.")


async def check_qdrant_health() -> dict[str, str | bool]:
    """Check Qdrant server health by querying collection lists."""
    try:
        client = get_qdrant_client()
        # Test basic connectivity to Qdrant cluster/collections
        await client.get_collections()
        return {"status": "healthy", "available": True}
    except Exception as exc:
        logger.warning(f"Qdrant health check failed: {exc}")
        return {"status": "unhealthy", "available": False, "error": str(exc)}
