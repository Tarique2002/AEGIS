"""Integration tests for Task API endpoints and complete AgentRuntime flow."""

import uuid

import pytest
from app.agents.service import TaskService
from app.api.v1.endpoints.tasks import get_task_service
from app.llm.providers.mock import MockLLMProvider
from app.main import app
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_and_execute_task_endpoint(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    # Override provider to ensure Mock provider is used in tests
    mock_provider = MockLLMProvider(
        default_response_text="PostgreSQL index scan reduces search complexity.",
        prompt_tokens=150,
        completion_tokens=60,
    )

    class CustomTestTaskService(TaskService):
        async def create_and_execute_task(self, task_in, session, provider=None):
            return await super().create_and_execute_task(
                task_in, session=session, provider=mock_provider
            )

    app.dependency_overrides[get_task_service] = lambda: CustomTestTaskService()

    payload = {
        "objective": "Explain how PostgreSQL indexing works.",
        "metadata": {"source": "integration_test"},
    }

    response = await async_client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "task_id" in data
    assert "run_id" in data
    assert data["status"] == "completed"
    assert data["objective"] == payload["objective"]
    assert "PostgreSQL index scan" in data["result"]
    assert data["telemetry"] is not None
    assert data["telemetry"]["total_tokens"] == 210

    task_id = data["task_id"]

    # 1. Test GET /api/v1/tasks/{task_id}
    get_resp = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 200
    task_data = get_resp.json()
    assert task_data["id"] == task_id
    assert task_data["status"] == "completed"
    assert task_data["result"] == data["result"]
    assert len(task_data["runs"]) == 1
    assert task_data["runs"][0]["status"] == "completed"

    # 2. Test GET /api/v1/tasks/{task_id}/events
    events_resp = await async_client.get(f"/api/v1/tasks/{task_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) >= 6

    # Verify monotonic sequencing
    seqs = [e["sequence_number"] for e in events]
    assert seqs == list(range(1, len(events) + 1))
    assert events[0]["event_type"] == "TASK_CREATED"
    assert events[1]["event_type"] == "RUN_STARTED"
    assert events[-1]["event_type"] == "TASK_COMPLETED"

    app.dependency_overrides.pop(get_task_service, None)


@pytest.mark.asyncio
async def test_get_task_not_found(async_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/tasks/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["type"] == "AegisNotFoundError"
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_create_task_validation_error(async_client: AsyncClient):
    payload = {"objective": "ab"}  # min_length is 3
    response = await async_client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["type"] == "RequestValidationError"


@pytest.mark.asyncio
async def test_create_task_provider_failure(async_client: AsyncClient):
    failing_provider = MockLLMProvider(
        should_fail=True,
        failure_message="Simulated LLM Provider failure",
    )

    class FailingTestTaskService(TaskService):
        async def create_and_execute_task(self, task_in, session, provider=None):
            return await super().create_and_execute_task(
                task_in, session=session, provider=failing_provider
            )

    app.dependency_overrides[get_task_service] = lambda: FailingTestTaskService()

    payload = {"objective": "Explain database indexes"}
    response = await async_client.post("/api/v1/tasks", json=payload)

    # Provider errors are converted to 502 Bad Gateway safely
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["type"] == "LLMProviderError"
    assert "Simulated LLM Provider failure" in data["error"]["message"]
    # Ensure no stack trace or secrets leaked
    assert "traceback" not in data

    app.dependency_overrides.pop(get_task_service, None)
