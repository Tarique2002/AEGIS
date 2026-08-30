"""FastAPI dependency providers for Safety Services and Safety Gates."""

from typing import Annotated

from fastapi import Depends

from app.observability.events import EventEmitter
from app.safety.gates import SafetyGate
from app.safety.policies import SafetyPolicy, get_default_safety_policy
from app.safety.service import SafetyService

_global_safety_service: SafetyService | None = None


def get_safety_policy() -> SafetyPolicy:
    """Get the active application safety policy."""
    return get_default_safety_policy()


def get_safety_service(
    policy: Annotated[SafetyPolicy, Depends(get_safety_policy)],
) -> SafetyService:
    """Provide singleton or contextual SafetyService instance."""
    global _global_safety_service
    if _global_safety_service is None:
        _global_safety_service = SafetyService(policy=policy, emitter=EventEmitter())
    return _global_safety_service


def get_safety_gate(
    policy: Annotated[SafetyPolicy, Depends(get_safety_policy)],
) -> SafetyGate:
    """Provide SafetyGate evaluator."""
    return SafetyGate(policy=policy)
