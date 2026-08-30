"""Integration tests for Safety Gate integration in Memory Service."""

import uuid

import pytest
from app.memory.errors import MemoryPolicyViolationError
from app.memory.schemas import MemoryCandidate, MemoryType
from app.memory.service import MemoryService
from app.safety.gates import SafetyGate
from app.safety.policies import SafetyPolicy
from app.safety.schemas import RiskLevel
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_memory_write_blocked_by_safety_gate(db_session: AsyncSession) -> None:
    # Memory writes are MEDIUM risk. Strict policy with max_risk_level=LOW blocks it.
    strict_policy = SafetyPolicy(max_risk_level=RiskLevel.LOW)
    safety_gate = SafetyGate(policy=strict_policy)
    memory_service = MemoryService(safety_gate=safety_gate)

    candidate = MemoryCandidate(
        content="Important fact to persist",
        memory_type=MemoryType.EPISODIC,
    )

    with pytest.raises(MemoryPolicyViolationError, match="Memory write safety denied"):
        await memory_service.remember(
            candidate=candidate,
            trusted_user_id=uuid.uuid4(),
            session=db_session,
        )
