"""Fake in-memory Redis and Qdrant client implementations for isolated unit testing."""

import fnmatch
import math
import time
from typing import Any


class FakeRedisClient:
    """Async in-memory fake Redis client supporting TTL and glob pattern key matching."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._expires: dict[str, float] = {}

    def _is_expired(self, key: str) -> bool:
        if key in self._expires:
            if time.time() > self._expires[key]:
                self._store.pop(key, None)
                self._expires.pop(key, None)
                return True
        return False

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        if nx and name in self._store and not self._is_expired(name):
            return False
        if xx and (name not in self._store or self._is_expired(name)):
            return False

        self._store[name] = str(value)
        if ex is not None:
            self._expires[name] = time.time() + ex
        elif px is not None:
            self._expires[name] = time.time() + (px / 1000.0)
        else:
            self._expires.pop(name, None)
        return True

    async def get(self, name: str) -> str | None:
        if self._is_expired(name):
            return None
        return self._store.get(name)

    async def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._store:
                self._store.pop(name, None)
                self._expires.pop(name, None)
                count += 1
        return count

    async def keys(self, pattern: str = "*") -> list[str]:
        matching: list[str] = []
        for k in list(self._store.keys()):
            if not self._is_expired(k):
                if fnmatch.fnmatch(k, pattern):
                    matching.append(k)
        return matching

    async def flushdb(self) -> bool:
        self._store.clear()
        self._expires.clear()
        return True

    async def ttl(self, name: str) -> int:
        if name not in self._store or self._is_expired(name):
            return -2
        if name in self._expires:
            remaining = int(self._expires[name] - time.time())
            return max(0, remaining)
        return -1


class FakeQdrantClient:
    """Async in-memory fake Qdrant client supporting collections, vector upsert, and search."""

    def __init__(self) -> None:
        self._collections: set[str] = set()
        self._points: dict[
            str, dict[str, Any]
        ] = {}  # {collection: {point_id: {id, vector, payload}}}

    async def get_collections(self) -> Any:
        class CollectionsResponse:
            def __init__(self, names):
                self.collections = [type("Col", (), {"name": n})() for n in names]

        return CollectionsResponse(list(self._collections))

    async def create_collection(self, collection_name: str, **kwargs) -> bool:
        self._collections.add(collection_name)
        if collection_name not in self._points:
            self._points[collection_name] = {}
        return True

    async def upsert(self, collection_name: str, points: list[Any]) -> Any:
        if collection_name not in self._points:
            self._points[collection_name] = {}
        for p in points:
            pid = str(p.id)
            self._points[collection_name][pid] = {
                "id": pid,
                "vector": p.vector,
                "payload": p.payload or {},
            }
        return True

    async def retrieve(
        self, collection_name: str, ids: list[str], with_payload: bool = True
    ) -> list[Any]:
        collection = self._points.get(collection_name, {})
        results = []
        for pid in ids:
            if str(pid) in collection:
                data = collection[str(pid)]
                point_obj = type("Point", (), {"id": data["id"], "payload": data["payload"]})()
                results.append(point_obj)
        return results

    async def delete(self, collection_name: str, points_selector: Any) -> Any:
        collection = self._points.get(collection_name, {})
        if hasattr(points_selector, "points"):
            for pid in points_selector.points:
                collection.pop(str(pid), None)
        return True

    async def scroll(
        self, collection_name: str, scroll_filter: Any = None, limit: int = 10, **kwargs
    ) -> tuple[list[Any], None]:
        collection = self._points.get(collection_name, {})
        matched = []
        for p in collection.values():
            if self._matches_filter(p["payload"], scroll_filter):
                point_obj = type("Point", (), {"id": p["id"], "payload": p["payload"]})()
                matched.append(point_obj)
                if len(matched) >= limit:
                    break
        return matched, None

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        query_filter: Any = None,
        limit: int = 10,
        score_threshold: float | None = None,
        **kwargs,
    ) -> list[Any]:
        collection = self._points.get(collection_name, {})
        scored: list[Any] = []

        for p in collection.values():
            if not self._matches_filter(p["payload"], query_filter):
                continue

            # Compute cosine similarity
            vec = p["vector"]
            sim = self._cosine_sim(query_vector, vec)
            if score_threshold is not None and sim < score_threshold:
                continue

            scored.append(
                type("ScoredPoint", (), {"id": p["id"], "score": sim, "payload": p["payload"]})()
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    def _matches_filter(self, payload: dict, filter_obj: Any) -> bool:
        if filter_obj is None:
            return True
        if hasattr(filter_obj, "must") and filter_obj.must:
            for cond in filter_obj.must:
                key = getattr(cond, "key", None)
                match = getattr(cond, "match", None)
                if key and match:
                    expected_val = getattr(match, "value", None)
                    if str(payload.get(key)) != str(expected_val):
                        return False
        return True

    def _cosine_sim(self, v1: list[float], v2: list[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)
