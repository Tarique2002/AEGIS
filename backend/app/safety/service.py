"""Central Application Service for safety gates, approvals, rate limiting, and audit logging."""

import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AegisNotFoundError
from app.core.logging import get_logger
from app.db.models.safety import ApprovalModel, SafetyAuditModel
from app.observability.events import EventEmitter
from app.safety.audit import SafetyAuditLogger
from app.safety.errors import (
    ApprovalExpiredError,
    CircuitOpenError,
    RateLimitExceededError,
    SafetyError,
    SafetyStoppedError,
)
from app.safety.gates import SafetyGate
from app.safety.manager import EmergencyStopController, SafetyCircuitBreaker
from app.safety.policies import SafetyPolicy, get_default_safety_policy
from app.safety.risk import RiskAssessmentEngine
from app.safety.schemas import (
    ApprovalCreateRequest,
    ApprovalResponse,
    ApprovalStatus,
    CircuitState,
    RateLimitResult,
    RiskLevel,
    SafetyAuditEvent,
    SafetyContext,
    SafetyDecision,
    SafetyDecisionType,
)
from app.schemas.common import utc_now
from app.schemas.event import ExecutionEventType

logger = get_logger("aegis.safety.service")

# In-memory sliding window rate-limit buckets (fallback when Redis is offline)
_local_rate_limit_buckets: dict[str, list[float]] = {}


class SafetyService:
    """
    Unified Safety and Platform Hardening Service.
    Enforces the 7-stage safety gate, manages human approvals, handles tenant rate limiting,
    tracks circuit breakers, emergency stops, and records append-only audit traces.
    """

    def __init__(
        self,
        policy: SafetyPolicy | None = None,
        emitter: EventEmitter | None = None,
        circuit_breaker: SafetyCircuitBreaker | None = None,
        emergency_stop: EmergencyStopController | None = None,
    ) -> None:
        self.policy = policy or get_default_safety_policy()
        self.emitter = emitter or EventEmitter()
        self.risk_engine = RiskAssessmentEngine(policy=self.policy)
        self.gate = SafetyGate(policy=self.policy, risk_engine=self.risk_engine)
        self.circuit_breaker = circuit_breaker or SafetyCircuitBreaker()
        self.emergency_stop = emergency_stop or EmergencyStopController()

    async def check_rate_limit(
        self,
        user_id: uuid.UUID,
        endpoint_type: str = "general",
        window_seconds: int = 60,
    ) -> RateLimitResult:
        """
        Check rate limit using tenant-scoped key:
        `aegis:ratelimit:user:{user_id}:{endpoint_type}`
        """
        if not settings.RATE_LIMIT_ENABLED:
            return RateLimitResult(
                allowed=True, limit=1000, remaining=999, reset_seconds=window_seconds
            )

        limits_map = {
            "auth": settings.AUTH_RATE_LIMIT,
            "general": settings.GENERAL_RATE_LIMIT,
            "tool": settings.TOOL_RATE_LIMIT,
            "orchestration": settings.ORCHESTRATION_RATE_LIMIT,
            "memory": settings.MEMORY_RATE_LIMIT,
        }
        max_allowed = limits_map.get(endpoint_type, settings.GENERAL_RATE_LIMIT)
        rate_key = f"aegis:ratelimit:user:{user_id}:{endpoint_type}"

        now = time.time()
        # Attempt Redis sliding window
        try:
            from app.db.redis import get_redis_client

            client = get_redis_client()
            pipe = client.pipeline()
            # Remove timestamps older than window
            pipe.zremrangebyscore(rate_key, 0, now - window_seconds)
            pipe.zadd(rate_key, {str(now): now})
            pipe.zcard(rate_key)
            pipe.expire(rate_key, window_seconds)
            results = await pipe.execute()
            count = results[2]

            remaining = max(0, max_allowed - count)
            allowed = count <= max_allowed
            retry_after = window_seconds if not allowed else 0

            return RateLimitResult(
                allowed=allowed,
                limit=max_allowed,
                remaining=remaining,
                reset_seconds=window_seconds,
                retry_after_seconds=retry_after,
            )
        except Exception:
            # Fallback to in-memory sliding window
            timestamps = _local_rate_limit_buckets.setdefault(rate_key, [])
            # Filter out expired
            _local_rate_limit_buckets[rate_key] = [
                t for t in timestamps if now - t < window_seconds
            ]
            timestamps = _local_rate_limit_buckets[rate_key]
            timestamps.append(now)

            count = len(timestamps)
            allowed = count <= max_allowed
            remaining = max(0, max_allowed - count)
            retry_after = window_seconds if not allowed else 0

            return RateLimitResult(
                allowed=allowed,
                limit=max_allowed,
                remaining=remaining,
                reset_seconds=window_seconds,
                retry_after_seconds=retry_after,
            )

    async def evaluate_action(
        self,
        context: SafetyContext,
        session: AsyncSession | None = None,
        rate_endpoint_type: str = "general",
    ) -> SafetyDecision:
        """
        Evaluate any action against emergency stops, circuit breakers, rate limits,
        and the 7-stage safety gate pipeline.
        """
        # 1. Check Emergency Stop
        if context.task_id and self.emergency_stop.is_stopped(context.task_id):
            raise SafetyStoppedError(
                f"Task '{context.task_id}' is locked under emergency safety stop."
            )
        if context.orchestration_id and self.emergency_stop.is_stopped(context.orchestration_id):
            raise SafetyStoppedError(
                f"Orchestration '{context.orchestration_id}' is locked under emergency safety stop."
            )

        # 2. Check Circuit Breaker
        breaker_key = context.tool_name or context.worker_id or str(context.user_id)
        circuit_state = self.circuit_breaker.get_state(breaker_key)
        if circuit_state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit breaker is OPEN for '{breaker_key}'. Request rejected."
            )

        # 3. Check Rate Limit
        rate_result = await self.check_rate_limit(context.user_id, endpoint_type=rate_endpoint_type)
        if not rate_result.allowed:
            await self.emitter.emit(
                task_id=context.task_id or uuid.uuid4(),
                run_id=context.run_id or uuid.uuid4(),
                event_type=ExecutionEventType.SAFETY_RATE_LIMITED,
                payload={
                    "endpoint_type": rate_endpoint_type,
                    "retry_after": rate_result.retry_after_seconds,
                },
                session=session,
            )
            raise RateLimitExceededError(
                f"Rate limit exceeded for '{rate_endpoint_type}'. "
                f"Retry in {rate_result.retry_after_seconds}s.",
                details={"retry_after": rate_result.retry_after_seconds},
            )

        # 4. Evaluate Safety Gates
        decision = await self.gate.evaluate(context, rate_limit_result=rate_result)

        # 5. Log append-only audit record
        await SafetyAuditLogger.log_decision(
            decision=decision,
            user_id=context.user_id,
            action=context.action,
            task_id=context.task_id,
            run_id=context.run_id,
            orchestration_id=context.orchestration_id,
            worker_id=context.worker_id,
            session=session,
        )

        # 6. Emit corresponding lifecycle events
        ev_type = (
            ExecutionEventType.SAFETY_GATE_PASSED
            if decision.allowed
            else ExecutionEventType.SAFETY_GATE_REJECTED
        )
        await self.emitter.emit(
            task_id=context.task_id or uuid.uuid4(),
            run_id=context.run_id or uuid.uuid4(),
            event_type=ev_type,
            payload={
                "action": context.action,
                "decision": decision.decision_type.value,
                "risk_level": decision.risk_level.value,
                "reason": decision.reason,
            },
            session=session,
        )

        return decision

    async def create_approval(
        self,
        request: ApprovalCreateRequest,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ApprovalResponse:
        """Create an explicit approval request for a high-risk action."""
        approval_id = uuid.uuid4()
        now = utc_now()
        expires_at = now + timedelta(seconds=self.policy.approval_ttl_seconds)

        model = ApprovalModel(
            id=approval_id,
            user_id=trusted_user_id,
            task_id=request.task_id,
            action=request.action,
            resource=request.resource,
            risk_level=request.risk_level.value,
            status=ApprovalStatus.PENDING.value,
            policy_version=self.policy.policy_version,
            requested_at=now,
            expires_at=expires_at,
            approval_metadata=request.metadata,
        )
        session.add(model)
        await session.flush()

        await self.emitter.emit(
            task_id=request.task_id or uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.SAFETY_APPROVAL_REQUESTED,
            payload={
                "approval_id": str(approval_id),
                "action": request.action,
                "risk_level": request.risk_level.value,
                "expires_at": expires_at.isoformat(),
            },
            session=session,
        )

        return self._to_approval_response(model)

    async def get_approval(
        self,
        approval_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ApprovalResponse:
        """Fetch approval status with multi-tenant ownership verification."""
        stmt = select(ApprovalModel).where(
            ApprovalModel.id == approval_id,
            ApprovalModel.user_id == trusted_user_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Approval request '{approval_id}' not found.")

        # Check expiration
        if model.status == ApprovalStatus.PENDING.value and self._is_expired(model.expires_at):
            model.status = ApprovalStatus.EXPIRED.value
            await session.flush()

        return self._to_approval_response(model)

    async def approve_action(
        self,
        approval_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ApprovalResponse:
        """Explicitly approve a pending high-risk action within expiration bounds."""
        stmt = select(ApprovalModel).where(
            ApprovalModel.id == approval_id,
            ApprovalModel.user_id == trusted_user_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Approval request '{approval_id}' not found.")

        if model.status == ApprovalStatus.EXPIRED.value or self._is_expired(model.expires_at):
            model.status = ApprovalStatus.EXPIRED.value
            await session.flush()
            raise ApprovalExpiredError("Approval request has expired.")

        if model.status != ApprovalStatus.PENDING.value:
            raise SafetyError(f"Cannot approve request in '{model.status}' state.")

        model.status = ApprovalStatus.APPROVED.value
        model.approved_at = utc_now()
        model.approved_by = str(trusted_user_id)
        await session.flush()

        await self.emitter.emit(
            task_id=model.task_id or uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.SAFETY_APPROVAL_GRANTED,
            payload={"approval_id": str(approval_id), "action": model.action},
            session=session,
        )

        return self._to_approval_response(model)

    async def deny_action(
        self,
        approval_id: uuid.UUID,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
    ) -> ApprovalResponse:
        """Explicitly deny an action approval request."""
        stmt = select(ApprovalModel).where(
            ApprovalModel.id == approval_id,
            ApprovalModel.user_id == trusted_user_id,
        )
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise AegisNotFoundError(f"Approval request '{approval_id}' not found.")

        model.status = ApprovalStatus.DENIED.value
        await session.flush()

        await self.emitter.emit(
            task_id=model.task_id or uuid.uuid4(),
            run_id=uuid.uuid4(),
            event_type=ExecutionEventType.SAFETY_APPROVAL_DENIED,
            payload={"approval_id": str(approval_id), "action": model.action},
            session=session,
        )

        return self._to_approval_response(model)

    async def get_audit_records(
        self,
        trusted_user_id: uuid.UUID,
        session: AsyncSession,
        limit: int = 50,
    ) -> list[SafetyAuditEvent]:
        """Query safety audit history with SQL query-level tenant filtering."""
        stmt = (
            select(SafetyAuditModel)
            .where(SafetyAuditModel.user_id == trusted_user_id)
            .order_by(SafetyAuditModel.created_at.desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        models = res.scalars().all()
        return [
            SafetyAuditEvent(
                audit_id=m.id,
                timestamp=m.created_at,
                user_id=m.user_id,
                task_id=m.task_id,
                run_id=m.run_id,
                orchestration_id=m.orchestration_id,
                worker_id=m.worker_id,
                action=m.action,
                decision=SafetyDecisionType(m.decision),
                risk_level=RiskLevel(m.risk_level),
                gate=m.gate,
                reason=m.reason,
                policy_version=m.policy_version,
                metadata=m.audit_metadata,
            )
            for m in models
        ]

    def _to_approval_response(self, model: ApprovalModel) -> ApprovalResponse:
        return ApprovalResponse(
            approval_id=model.id,
            user_id=model.user_id,
            task_id=model.task_id,
            action=model.action,
            resource=model.resource,
            risk_level=RiskLevel(model.risk_level),
            reason=model.approval_metadata.get("reason", "Explicit action approval requested."),
            status=ApprovalStatus(model.status),
            policy_version=model.policy_version,
            requested_at=model.requested_at,
            expires_at=model.expires_at,
            approved_at=model.approved_at,
            approved_by=model.approved_by,
            metadata=model.approval_metadata,
        )

    @staticmethod
    def _is_expired(expires_at: datetime) -> bool:
        now = utc_now()
        if expires_at.tzinfo is None:
            return now.replace(tzinfo=None) > expires_at
        return now > expires_at
