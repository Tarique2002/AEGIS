"""Redis connection client and health check abstraction."""

import logging

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

logger = logging.getLogger("aegis.redis")

# Global Redis connection pool
_redis_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    """Get or initialize the global Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            settings.redis_connection_url,
            socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
            socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    return _redis_pool


def get_redis_client() -> Redis:
    """Get an asynchronous Redis client instance."""
    return Redis(connection_pool=get_redis_pool())


async def close_redis() -> None:
    """Close the global Redis connection pool on shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Closed Redis connection pool.")


async def check_redis_health() -> dict[str, str | bool]:
    """Check Redis server health via PING command."""
    try:
        client = get_redis_client()
        pong = await client.ping()
        if pong is True or pong == "PONG":
            return {"status": "healthy", "available": True}
        return {"status": "unhealthy", "available": False, "error": "Unexpected PING response"}
    except Exception as exc:
        logger.warning(f"Redis health check failed: {exc}")
        return {"status": "unhealthy", "available": False, "error": str(exc)}
