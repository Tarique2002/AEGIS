"""Integration tests for health and readiness endpoints."""

from httpx import AsyncClient


async def test_liveness_endpoint(async_client: AsyncClient):
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert data["app_name"] == "AEGIS"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


async def test_api_v1_liveness_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"


async def test_readiness_all_healthy(async_client: AsyncClient, monkeypatch):
    # Mock healthy responses for all dependencies
    async def mock_db_healthy():
        return {"status": "healthy", "available": True}

    async def mock_redis_healthy():
        return {"status": "healthy", "available": True}

    async def mock_qdrant_healthy():
        return {"status": "healthy", "available": True}

    monkeypatch.setattr("app.api.v1.endpoints.health.check_database_health", mock_db_healthy)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_redis_health", mock_redis_healthy)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_qdrant_health", mock_qdrant_healthy)

    response = await async_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] == "healthy"
    assert data["dependencies"]["redis"] == "healthy"
    assert data["dependencies"]["qdrant"] == "healthy"


async def test_readiness_dependency_unhealthy(async_client: AsyncClient, monkeypatch):
    async def mock_db_healthy():
        return {"status": "healthy", "available": True}

    async def mock_redis_unhealthy():
        return {"status": "unhealthy", "available": False, "error": "Connection refused"}

    async def mock_qdrant_healthy():
        return {"status": "healthy", "available": True}

    monkeypatch.setattr("app.api.v1.endpoints.health.check_database_health", mock_db_healthy)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_redis_health", mock_redis_unhealthy)
    monkeypatch.setattr("app.api.v1.endpoints.health.check_qdrant_health", mock_qdrant_healthy)

    response = await async_client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["dependencies"]["database"] == "healthy"
    assert data["dependencies"]["redis"] == "unhealthy"
    assert data["dependencies"]["qdrant"] == "healthy"
