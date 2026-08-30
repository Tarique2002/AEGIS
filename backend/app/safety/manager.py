"""Circuit Breaker and Emergency Stop state managers for platform resilience."""

import time
import uuid
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.safety.schemas import CircuitState

logger = get_logger("aegis.safety.manager")


class SafetyCircuitBreaker:
    """
    Circuit breaker tracking failure rates per resource/worker/tool/user.
    State transitions: CLOSED -> OPEN -> HALF_OPEN (after cooldown) -> CLOSED.
    """

    def __init__(
        self,
        failure_threshold: int = settings.CIRCUIT_BREAKER_THRESHOLD,
        cooldown_seconds: float = settings.CIRCUIT_BREAKER_COOLDOWN,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures: dict[str, int] = {}
        self._state: dict[str, CircuitState] = {}
        self._tripped_at: dict[str, float] = {}

    def get_state(self, key: str) -> CircuitState:
        """Get current circuit breaker state for a resource key."""
        current_state = self._state.get(key, CircuitState.CLOSED)
        if current_state == CircuitState.OPEN:
            tripped_time = self._tripped_at.get(key, 0.0)
            if time.time() - tripped_time >= self.cooldown_seconds:
                self._state[key] = CircuitState.HALF_OPEN
                return CircuitState.HALF_OPEN
        return current_state

    def record_success(self, key: str) -> None:
        """Record successful execution, resetting failure counters."""
        self._failures[key] = 0
        self._state[key] = CircuitState.CLOSED

    def record_failure(self, key: str) -> CircuitState:
        """Record execution failure, potentially tripping circuit to OPEN."""
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker TRIPPED to OPEN for key '{key}' after {count} "
                "consecutive failures."
            )
            self._state[key] = CircuitState.OPEN
            self._tripped_at[key] = time.time()
            return CircuitState.OPEN
        return self._state.get(key, CircuitState.CLOSED)


class EmergencyStopController:
    """Manages active emergency freeze locks for tasks, loops, and orchestrations."""

    def __init__(self) -> None:
        self._stopped_entities: dict[uuid.UUID, dict[str, Any]] = {}

    def is_stopped(self, entity_id: uuid.UUID) -> bool:
        """Check if an entity is currently under an emergency stop lock."""
        return entity_id in self._stopped_entities

    def trigger_stop(
        self,
        entity_id: uuid.UUID,
        reason: str,
        triggered_by: str = "SafetySystem",
    ) -> None:
        """Lock an entity under emergency safety stop."""
        logger.critical(
            f"EMERGENCY SAFETY STOP triggered for entity {entity_id}: {reason} by {triggered_by}"
        )
        self._stopped_entities[entity_id] = {
            "entity_id": entity_id,
            "reason": reason,
            "triggered_by": triggered_by,
            "stopped_at": time.time(),
        }

    def clear_stop(self, entity_id: uuid.UUID) -> bool:
        """Clear an emergency stop lock upon verified explicit administrative intervention."""
        if entity_id in self._stopped_entities:
            del self._stopped_entities[entity_id]
            logger.info(f"Emergency safety stop CLEARED for entity {entity_id}")
            return True
        return False
