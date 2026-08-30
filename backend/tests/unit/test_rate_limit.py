"""Unit tests for tenant rate limiting."""

import uuid

import pytest
from app.safety.service import SafetyService


@pytest.mark.asyncio
async def test_tenant_rate_limiting_sliding_window() -> None:
    service = SafetyService()
    user_id = uuid.uuid4()

    # Repeated calls up to limit
    for _ in range(10):
        res = await service.check_rate_limit(user_id=user_id, endpoint_type="orchestration")
        assert res.allowed is True

    # 11th call exceeds limit (10 for orchestration)
    res_exceeded = await service.check_rate_limit(user_id=user_id, endpoint_type="orchestration")
    assert res_exceeded.allowed is False
    assert res_exceeded.retry_after_seconds > 0
