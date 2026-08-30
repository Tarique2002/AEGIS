"""Thread-safe, tenant-isolated compiled policy cache."""

import threading
import uuid
from typing import Any


class CompiledPolicyCache:
    """
    In-memory cache for compiled CEL policy ASTs.
    Keyed strictly by (tenant_id, policy_id, policy_version) to prevent cross-tenant leakage.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[uuid.UUID, uuid.UUID, str], Any] = {}
        self._lock = threading.Lock()

    def get(
        self,
        tenant_id: uuid.UUID,
        policy_id: uuid.UUID,
        version: str,
    ) -> Any | None:
        """Retrieve compiled AST if present in cache."""
        with self._lock:
            return self._cache.get((tenant_id, policy_id, version))

    def set(
        self,
        tenant_id: uuid.UUID,
        policy_id: uuid.UUID,
        version: str,
        ast: Any,
    ) -> None:
        """Cache compiled AST for tenant policy version."""
        with self._lock:
            self._cache[(tenant_id, policy_id, version)] = ast

    def invalidate(self, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> None:
        """Invalidate all cached versions of a specific policy for tenant."""
        with self._lock:
            keys_to_delete = [k for k in self._cache if k[0] == tenant_id and k[1] == policy_id]
            for k in keys_to_delete:
                self._cache.pop(k, None)

    def clear_tenant(self, tenant_id: uuid.UUID) -> None:
        """Clear all cached policies for a tenant."""
        with self._lock:
            keys_to_delete = [k for k in self._cache if k[0] == tenant_id]
            for k in keys_to_delete:
                self._cache.pop(k, None)

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
