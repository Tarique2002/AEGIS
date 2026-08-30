"""Integration tests for Tool API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_tools_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/tools")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    tool_names = [tool["name"] for tool in data]
    assert "calculator" in tool_names


@pytest.mark.asyncio
async def test_get_tool_by_name_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/tools/calculator")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "calculator"
    assert data["policy_level"] == "SAFE"
    assert "expression" in data["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_get_tool_not_found(async_client: AsyncClient):
    response = await async_client.get("/api/v1/tools/non_existent_tool")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["type"] == "ToolNotFoundError"


@pytest.mark.asyncio
async def test_execute_tool_endpoint_success(async_client: AsyncClient):
    payload = {
        "tool_name": "calculator",
        "arguments": {"expression": "(25 * 4) + 10"},
    }
    response = await async_client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["status"] == "completed"
    assert data["tool_name"] == "calculator"
    assert data["output"]["result"] == 110
    assert data["error"] is None
    assert data["duration_ms"] > 0


@pytest.mark.asyncio
async def test_execute_tool_endpoint_unsafe_expression_rejection(async_client: AsyncClient):
    payload = {
        "tool_name": "calculator",
        "arguments": {"expression": "__import__('os').system('ls')"},
    }
    response = await async_client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert data["status"] == "rejected"
    assert "Forbidden expression syntax" in data["error"]


@pytest.mark.asyncio
async def test_execute_tool_endpoint_division_by_zero(async_client: AsyncClient):
    payload = {
        "tool_name": "calculator",
        "arguments": {"expression": "100 / 0"},
    }
    response = await async_client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert data["status"] == "failed"
    assert "Division by zero" in data["error"]
