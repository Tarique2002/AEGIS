"""Procedural Memory Store foundation for reusable task procedures and execution blueprints."""

import uuid

from app.memory.base import BaseMemoryStore
from app.memory.schemas import (
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryType,
    ProceduralMemoryRecord,
)


class ProceduralMemoryStore(BaseMemoryStore):
    """
    Procedural Memory Store.
    Maintains structured blueprints, strategies, and step-by-step procedures.
    """

    def __init__(self) -> None:
        self._procedures: dict[str, ProceduralMemoryRecord] = {}

    @property
    def memory_type(self) -> MemoryType:
        return MemoryType.PROCEDURAL

    async def register_procedure(
        self,
        procedure: ProceduralMemoryRecord,
    ) -> ProceduralMemoryRecord:
        """Register a procedural blueprint."""
        self._procedures[str(procedure.procedure_id)] = procedure
        return procedure

    async def get_procedure(
        self,
        procedure_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProceduralMemoryRecord | None:
        """Retrieve procedure by ID with user isolation."""
        proc = self._procedures.get(str(procedure_id))
        if proc and str(proc.user_id) == str(user_id):
            return proc
        return None

    async def list_procedures(
        self,
        user_id: uuid.UUID,
    ) -> list[ProceduralMemoryRecord]:
        """List all procedures owned by the specified user."""
        return [p for p in self._procedures.values() if str(p.user_id) == str(user_id)]

    # --- BaseMemoryStore Interface Implementations ---

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        """Store MemoryRecord as a procedural record."""
        steps = record.metadata.get("steps", [])
        name = record.metadata.get("name", record.content[:50])
        description = record.content

        proc = ProceduralMemoryRecord(
            procedure_id=record.memory_id,
            user_id=record.user_id,
            name=name,
            description=description,
            steps=steps,
            version=record.metadata.get("version", 1),
            importance=record.importance,
            metadata=record.metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        await self.register_procedure(proc)
        return record

    async def get(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MemoryRecord | None:
        """Retrieve procedural memory as a generic MemoryRecord."""
        proc = await self.get_procedure(memory_id, user_id)
        if not proc:
            return None
        return self._procedure_to_memory_record(proc)

    async def delete(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete procedural memory record."""
        proc = await self.get_procedure(memory_id, user_id)
        if not proc:
            return False
        del self._procedures[str(memory_id)]
        return True

    async def search(
        self,
        query: MemorySearchQuery,
    ) -> list[MemorySearchResult]:
        """Search procedural blueprints by name or description for trusted user."""
        user_id = query.user_id
        if not user_id:
            return []

        query_lower = query.query_text.lower()
        results: list[MemorySearchResult] = []

        for proc in self._procedures.values():
            if str(proc.user_id) != str(user_id):
                continue
            if query_lower in proc.name.lower() or query_lower in proc.description.lower():
                rec = self._procedure_to_memory_record(proc)
                results.append(
                    MemorySearchResult(
                        record=rec,
                        score=rec.importance,
                        matched_by="procedural_match",
                        similarity_score=0.9,
                        recency_score=1.0,
                        importance_score=rec.importance,
                    )
                )

        return results[: query.limit]

    def _procedure_to_memory_record(self, proc: ProceduralMemoryRecord) -> MemoryRecord:
        return MemoryRecord(
            memory_id=proc.procedure_id,
            memory_type=MemoryType.PROCEDURAL,
            user_id=proc.user_id,
            content=f"{proc.name}: {proc.description}",
            importance=proc.importance,
            metadata={
                "name": proc.name,
                "description": proc.description,
                "steps": proc.steps,
                "version": proc.version,
                **proc.metadata,
            },
            created_at=proc.created_at,
            updated_at=proc.updated_at,
        )
