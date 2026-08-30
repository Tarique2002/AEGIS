"""Unit tests for tenant-isolated CompiledPolicyCache."""

import uuid

import pytest
from app.authz.abac.cache import CompiledPolicyCache


@pytest.mark.asyncio
async def test_policy_cache_isolation_and_invalidation() -> None:
    cache = CompiledPolicyCache()
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    policy_id = uuid.uuid4()

    mock_ast_a = {"ast": "for_tenant_a"}
    mock_ast_b = {"ast": "for_tenant_b"}

    # Set cache for both tenants
    cache.set(tenant_a, policy_id, "1.0.0", mock_ast_a)
    cache.set(tenant_b, policy_id, "1.0.0", mock_ast_b)

    # Verify isolated retrieval
    assert cache.get(tenant_a, policy_id, "1.0.0") == mock_ast_a
    assert cache.get(tenant_b, policy_id, "1.0.0") == mock_ast_b

    # Invalidate tenant_a
    cache.invalidate(tenant_a, policy_id)
    assert cache.get(tenant_a, policy_id, "1.0.0") is None
    assert cache.get(tenant_b, policy_id, "1.0.0") == mock_ast_b
