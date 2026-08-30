"""
Memory Service layer providing application boundary, trusted context enforcement,
and event emission.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.errors import MemoryPolicyViolationError, MemoryValidationError
from app.memory.manager import MemoryManager
from app.memory.policies import MemoryPolicy
from app.memory.schemas import (
    MemoryCandidate,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryType,
)
from app.observability.events import EventEmitter
from app.schemas.event import ExecutionEventType


class MemoryService:
    """
    Application service boundary for memory operations.
    Enforces that all requests originate from trusted context and emit trace events.
    """

    def __init__(
        self,
        manager: MemoryManager | None = None,
        emitter: EventEmitter | None = None,
        policy: MemoryPolicy | None = None,
        safety_gate: Any | None = None,
    ) -> None:
        self.policy = policy or MemoryPolicy()
        self.manager = manager or MemoryManager(policy=self.policy)
        self.emitter = emitter or EventEmitter()
        self.safety_gate = safety_gate

    async def remember(
        self,
        candidate: MemoryCandidate,
        trusted_user_id: uuid.UUID,
        task_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> MemoryRecord:
        """Store a proposed memory candidate with event tracing."""
        eff_task_id = task_id or candidate.task_id or uuid.uuid4()
        eff_run_id = run_id or candidate.run_id or uuid.uuid4()

        # Safety Gate Evaluation (Phase 8)
        if self.safety_gate:
            from app.safety.schemas import SafetyContext

            s_ctx = SafetyContext(
                user_id=trusted_user_id,
                task_id=eff_task_id,
                run_id=eff_run_id,
                action="memory_write",
                arguments_metadata={"memory_type": candidate.memory_type.value},
            )
            decision = await self.safety_gate.evaluate(s_ctx)
            if not decision.allowed:
                raise MemoryPolicyViolationError(f"Memory write safety denied: {decision.reason}")

        await self._emit_event(
            task_id=eff_task_id,
            run_id=eff_run_id,
            event_type=ExecutionEventType.MEMORY_WRITE_STARTED,
            payload={
                "memory_type": candidate.memory_type.value,
                "content_preview": candidate.content[:100],
            },
            session=session,
        )

        try:
            record = await self.manager.remember(candidate, user_id=trusted_user_id)

            await self._emit_event(
                task_id=eff_task_id,
                run_id=eff_run_id,
                event_type=ExecutionEventType.MEMORY_WRITE_COMPLETED,
                payload={
                    "memory_id": str(record.memory_id),
                    "memory_type": record.memory_type.value,
                },
                session=session,
            )
            return record

        except (MemoryPolicyViolationError, MemoryValidationError) as exc:
            await self._emit_event(
                task_id=eff_task_id,
                run_id=eff_run_id,
                event_type=ExecutionEventType.MEMORY_WRITE_REJECTED,
                payload={"reason": exc.message, "memory_type": candidate.memory_type.value},
                session=session,
            )
            raise

    async def recall(
        self,
        query: MemorySearchQuery,
        trusted_user_id: uuid.UUID,
        task_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> list[MemorySearchResult]:
        """Recall relevant memories with event tracing."""
        eff_task_id = task_id or uuid.uuid4()
        eff_run_id = run_id or uuid.uuid4()

        await self._emit_event(
            task_id=eff_task_id,
            run_id=eff_run_id,
            event_type=ExecutionEventType.MEMORY_RETRIEVAL_STARTED,
            payload={"query_text": query.query_text[:100], "limit": query.limit},
            session=session,
        )

        results = await self.manager.recall(query, user_id=trusted_user_id)

        await self._emit_event(
            task_id=eff_task_id,
            run_id=eff_run_id,
            event_type=ExecutionEventType.MEMORY_RETRIEVAL_COMPLETED,
            payload={"results_count": len(results)},
            session=session,
        )
        return results

    async def get_memory(
        self,
        memory_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        memory_type: MemoryType | None = None,
    ) -> MemoryRecord:
        """Retrieve memory by ID for the trusted user."""
        return await self.manager.get_by_id(
            memory_id, user_id=trusted_user_id, memory_type=memory_type
        )

    async def forget_memory(
        self,
        memory_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        task_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        memory_type: MemoryType | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        """Delete memory item for the trusted user with event tracing."""
        eff_task_id = task_id or uuid.uuid4()
        eff_run_id = run_id or uuid.uuid4()

        success = await self.manager.forget(
            memory_id, user_id=trusted_user_id, memory_type=memory_type
        )
        if success:
            await self._emit_event(
                task_id=eff_task_id,
                run_id=eff_run_id,
                event_type=ExecutionEventType.MEMORY_DELETED,
                payload={"memory_id": str(memory_id)},
                session=session,
            )
        return success

    async def _emit_event(
        self,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        event_type: ExecutionEventType,
        payload: dict,
        session: AsyncSession | None,
    ) -> None:
        await self.emitter.emit(
            task_id=task_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            session=session,
        )
