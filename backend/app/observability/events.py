"""Execution event emission, sequencing, and persistence engine."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.event import ExecutionEventModel
from app.schemas.event import ExecutionEvent, ExecutionEventType

logger = get_logger("aegis.observability.events")


class EventEmitter:
    """
    Event emitter managing monotonically increasing sequence numbers per run_id
    and coordinating event persistence to PostgreSQL.
    """

    def __init__(self) -> None:
        self._sequence_counters: dict[uuid.UUID, int] = {}
        self._in_memory_events: list[ExecutionEvent] = []

    def _get_next_sequence_number(self, run_id: uuid.UUID) -> int:
        current = self._sequence_counters.get(run_id, 0)
        next_seq = current + 1
        self._sequence_counters[run_id] = next_seq
        return next_seq

    def _sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive credentials/secrets from event payload before persistence/streaming."""
        sanitized: dict[str, Any] = {}
        sensitive_keys = {
            "api_key",
            "secret",
            "password",
            "authorization",
            "bearer",
            "access_token",
            "refresh_token",
            "auth_token",
        }

        for k, v in payload.items():
            k_lower = k.lower()
            if any(s in k_lower for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_payload(v)
            else:
                sanitized[k] = v
        return sanitized

    async def emit(
        self,
        task_id: uuid.UUID,
        run_id: uuid.UUID,
        event_type: ExecutionEventType,
        payload: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> ExecutionEvent:
        """
        Create, sequence, log, and persist an execution lifecycle event.
        """
        seq = self._get_next_sequence_number(run_id)
        clean_payload = self._sanitize_payload(payload or {})

        event = ExecutionEvent(
            task_id=task_id,
            run_id=run_id,
            event_type=event_type,
            sequence_number=seq,
            payload=clean_payload,
        )

        self._in_memory_events.append(event)
        logger.debug(
            f"Event [{seq}] {event_type.value} for Task {task_id} / Run {run_id}",
            extra={"event_type": event_type.value, "sequence": seq},
        )

        if session is not None:
            db_event = ExecutionEventModel(
                id=event.event_id,
                task_id=event.task_id,
                run_id=event.run_id,
                event_type=event.event_type.value,
                sequence_number=event.sequence_number,
                payload=event.payload,
                timestamp=event.timestamp,
            )
            session.add(db_event)

        return event

    def get_events_for_run(self, run_id: uuid.UUID) -> list[ExecutionEvent]:
        """Return all recorded in-memory events for a specific run in chronological order."""
        return [e for e in self._in_memory_events if e.run_id == run_id]

    def get_events_for_task(self, task_id: uuid.UUID) -> list[ExecutionEvent]:
        """Return all recorded in-memory events for a specific task in sequence order."""
        return [e for e in self._in_memory_events if e.task_id == task_id]
