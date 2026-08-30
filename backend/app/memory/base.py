"""Base interfaces for memory storage layers."""

import uuid
from abc import ABC, abstractmethod

from app.memory.schemas import MemoryRecord, MemorySearchQuery, MemorySearchResult, MemoryType


class BaseMemoryStore(ABC):
    """Abstract interface that all memory stores must implement."""

    @property
    @abstractmethod
    def memory_type(self) -> MemoryType:
        """Return the memory tier handled by this store."""
        ...

    @abstractmethod
    async def store(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a memory record into the store."""
        ...

    @abstractmethod
    async def get(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> MemoryRecord | None:
        """Retrieve a memory record by ID with mandatory user isolation."""
        ...

    @abstractmethod
    async def delete(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a memory record by ID with mandatory user isolation."""
        ...

    @abstractmethod
    async def search(self, query: MemorySearchQuery) -> list[MemorySearchResult]:
        """Search relevant memories matching query criteria with user isolation."""
        ...
