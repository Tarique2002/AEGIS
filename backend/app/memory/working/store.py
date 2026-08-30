"""Redis-backed Working Memory Store with centralized key isolation and TTL support."""

import json
import uuid
from typing import Any

from redis.asyncio import Redis

from app.db.redis import get_redis_client
from app.memory.base import BaseMemoryStore
from app.memory.errors import MemoryStorageError
from app.memory.schemas import (
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryType,
)


class WorkingMemoryKeyBuilder:
    """Centralized key builder ensuring strict user and task namespace isolation in Redis."""

    PREFIX = "aegis:memory:working"

    @classmethod
    def build_key(
        cls,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        key: str,
    ) -> str:
        """Construct isolated Redis key for a specific user, task, and entry key."""
        return f"{cls.PREFIX}:{str(user_id)}:{str(task_id)}:{key}"

    @classmethod
    def build_task_pattern(
        cls,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
    ) -> str:
        """Construct Redis glob pattern matching all keys for a specific user and task."""
        return f"{cls.PREFIX}:{str(user_id)}:{str(task_id)}:*"


class WorkingMemoryStore(BaseMemoryStore):
    """
    Working Memory Store backed by Redis.
    Provides fast, short-lived, task/user-scoped scratchpad storage with TTL expiration.
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        default_ttl_seconds: int = 3600,
    ) -> None:
        self._redis = redis_client
        self.default_ttl_seconds = default_ttl_seconds

    @property
    def redis(self) -> Redis:
        """Get the active Redis client instance."""
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    @property
    def memory_type(self) -> MemoryType:
        return MemoryType.WORKING

    async def set_item(
        self,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Set a working memory key-value pair with TTL."""
        redis_key = WorkingMemoryKeyBuilder.build_key(user_id, task_id, key)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        try:
            serialized = json.dumps(value)
            await self.redis.set(redis_key, serialized, ex=ttl)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to write working memory to Redis: {exc}") from exc

    async def get_item(
        self,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        key: str,
    ) -> Any | None:
        """Get a working memory item value by key."""
        redis_key = WorkingMemoryKeyBuilder.build_key(user_id, task_id, key)
        try:
            data = await self.redis.get(redis_key)
            if data is None:
                return None
            return json.loads(data)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to read working memory from Redis: {exc}") from exc

    async def delete_item(
        self,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        key: str,
    ) -> bool:
        """Delete a working memory item by key."""
        redis_key = WorkingMemoryKeyBuilder.build_key(user_id, task_id, key)
        try:
            deleted_count = await self.redis.delete(redis_key)
            return bool(deleted_count > 0)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to delete working memory from Redis: {exc}") from exc

    async def clear_task_memory(
        self,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
    ) -> int:
        """Clear all working memory items for a specific user and task."""
        pattern = WorkingMemoryKeyBuilder.build_task_pattern(user_id, task_id)
        try:
            keys = await self.redis.keys(pattern)
            if not keys:
                return 0
            return int(await self.redis.delete(*keys))
        except Exception as exc:
            raise MemoryStorageError(f"Failed to clear task working memory: {exc}") from exc

    async def list_task_keys(
        self,
        user_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
    ) -> list[str]:
        """List all item keys stored for a given user and task."""
        pattern = WorkingMemoryKeyBuilder.build_task_pattern(user_id, task_id)
        prefix = f"{WorkingMemoryKeyBuilder.PREFIX}:{str(user_id)}:{str(task_id)}:"
        try:
            full_keys = await self.redis.keys(pattern)
            return [
                k[len(prefix) :] if isinstance(k, str) else k.decode("utf-8")[len(prefix) :]
                for k in full_keys
            ]
        except Exception as exc:
            raise MemoryStorageError(f"Failed to list task working memory keys: {exc}") from exc

    # --- BaseMemoryStore Interface Implementations ---

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        """Store standard MemoryRecord in working memory."""
        task_id = record.task_id or uuid.UUID(int=0)
        key = str(record.memory_id)
        payload = record.model_dump(mode="json")
        await self.set_item(
            user_id=record.user_id,
            task_id=task_id,
            key=key,
            value=payload,
            ttl_seconds=self.default_ttl_seconds,
        )
        return record

    async def get(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> MemoryRecord | None:
        """Retrieve MemoryRecord from working memory across tasks for this user."""
        pattern = f"{WorkingMemoryKeyBuilder.PREFIX}:{str(user_id)}:*:{str(memory_id)}"
        try:
            keys = await self.redis.keys(pattern)
            if not keys:
                return None
            data = await self.redis.get(keys[0])
            if not data:
                return None
            raw = json.loads(data)
            return MemoryRecord.model_validate(raw)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to get working memory record: {exc}") from exc

    async def delete(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete MemoryRecord from working memory."""
        pattern = f"{WorkingMemoryKeyBuilder.PREFIX}:{str(user_id)}:*:{str(memory_id)}"
        try:
            keys = await self.redis.keys(pattern)
            if not keys:
                return False
            deleted = await self.redis.delete(*keys)
            return bool(deleted > 0)
        except Exception as exc:
            raise MemoryStorageError(f"Failed to delete working memory record: {exc}") from exc

    async def search(self, query: MemorySearchQuery) -> list[MemorySearchResult]:
        """Search working memory records for the given user."""
        user_id = query.user_id
        if not user_id:
            return []

        pattern = f"{WorkingMemoryKeyBuilder.PREFIX}:{str(user_id)}:*"
        results: list[MemorySearchResult] = []
        try:
            keys = await self.redis.keys(pattern)
            query_lower = query.query_text.lower()

            for k in keys[: query.limit * 2]:
                val = await self.redis.get(k)
                if not val:
                    continue
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict) and "content" in parsed:
                        rec = MemoryRecord.model_validate(parsed)
                        if query_lower in rec.content.lower():
                            results.append(
                                MemorySearchResult(
                                    record=rec,
                                    score=1.0,
                                    matched_by="working_exact_keyword",
                                    similarity_score=1.0,
                                    recency_score=1.0,
                                    importance_score=rec.importance,
                                )
                            )
                except Exception:
                    continue
            return results[: query.limit]
        except Exception as exc:
            raise MemoryStorageError(f"Failed to search working memory: {exc}") from exc
