"""Domain exceptions and FastAPI exception handlers."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("aegis.errors")


class AegisException(Exception):
    """Base domain exception for AEGIS."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AegisValidationError(AegisException):
    """Raised when domain validation fails."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class AegisNotFoundError(AegisException):
    """Raised when a requested resource is not found."""

    status_code = status.HTTP_404_NOT_FOUND


class AegisAuthenticationError(AegisException):
    """Raised when authentication fails."""

    status_code = status.HTTP_401_UNAUTHORIZED


class AegisAuthorizationError(AegisException):
    """Raised when an action is forbidden."""

    status_code = status.HTTP_403_FORBIDDEN


class InfrastructureError(AegisException):
    """Raised when an underlying infrastructure dependency fails."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class DatabaseConnectionError(InfrastructureError):
    """Raised when PostgreSQL connection fails."""

    pass


class RedisConnectionError(InfrastructureError):
    """Raised when Redis connection fails."""

    pass


class QdrantConnectionError(InfrastructureError):
    """Raised when Qdrant connection fails."""

    pass


class ExternalServiceError(AegisException):
    """Raised when an upstream external service (e.g. LLM provider) fails."""

    status_code = status.HTTP_502_BAD_GATEWAY


class InvalidStateTransitionError(AegisValidationError):
    """Raised when an invalid state transition is attempted."""

    status_code = status.HTTP_409_CONFLICT


class LLMProviderError(ExternalServiceError):
    """Raised when an LLM provider fails during invocation."""

    status_code = status.HTTP_502_BAD_GATEWAY


class LLMTimeoutError(ExternalServiceError):
    """Raised when an LLM provider call times out."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT


class ModelResponseValidationError(AegisValidationError):
    """Raised when structured LLM output fails schema validation."""

    status_code = status.HTTP_502_BAD_GATEWAY


# ==============================================================================
# Evaluation & Reflection Exceptions (Phase 4)
# ==============================================================================


class EvaluationError(AegisException):
    """Base exception for evaluation engine failures."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class EvaluationNotFoundError(AegisNotFoundError):
    """Raised when an evaluation record is not found."""

    status_code = status.HTTP_404_NOT_FOUND


class EvaluationValidationError(AegisValidationError):
    """Raised when evaluation inputs, criteria, or scores fail validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class EvaluationPolicyViolationError(AegisValidationError):
    """Raised when evaluation violates platform safety or evaluation policy."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class EvaluationExecutionError(EvaluationError):
    """Raised when an evaluation execution pass encounters an unhandled runtime failure."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ReflectionError(AegisException):
    """Base exception for reflection engine failures."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ReflectionValidationError(AegisValidationError):
    """Raised when reflection inputs or parameters fail validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


# ==============================================================================
# Planner & Execution Graph Exceptions (Phase 5)
# ==============================================================================


class PlannerError(AegisException):
    """Base exception for planner subsystem failures."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class PlanValidationError(AegisValidationError):
    """Raised when a plan structure, node schema, or limit check fails validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class CyclicDependencyError(PlanValidationError):
    """Raised when an execution graph contains a cycle or invalid circular dependency."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class PlanNotFoundError(AegisNotFoundError):
    """Raised when an execution plan or checkpoint is not found."""

    status_code = status.HTTP_404_NOT_FOUND


class PlanExecutionError(PlannerError):
    """Raised when graph execution encounters a fatal execution failure."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class NodeExecutionError(PlanExecutionError):
    """Raised when a specific plan node execution fails unrecoverably."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class PlanCancellationError(PlanExecutionError):
    """Raised when a plan execution is cancelled or interrupted."""

    status_code = status.HTTP_409_CONFLICT


class CheckpointError(PlannerError):
    """Raised when checkpoint serialization, persistence, or recovery fails."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


# ==============================================================================
# Controlled Autonomous Agent Loop Exceptions (Phase 6)
# ==============================================================================


class AgentLoopError(AegisException):
    """Base exception for autonomous agent loop errors."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class AgentLoopNotFoundError(AegisNotFoundError):
    """Raised when an agent loop or iteration record is not found."""

    status_code = status.HTTP_404_NOT_FOUND


class BudgetExceededError(AgentLoopError):
    """Raised when an agent loop execution exhausts its allocated resource budget."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class StagnationDetectedError(AgentLoopError):
    """Raised when loop progress halts or exhibits repetitive no-op cycles."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class SafetyStopTriggeredError(AgentLoopError):
    """Raised when a safety policy, guardrail, or risk condition forces a loop halt."""

    status_code = status.HTTP_403_FORBIDDEN


class InvalidDecisionError(AegisValidationError):
    """Raised when an agent decision proposal is malformed, invalid, or violates policy."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ApprovalRequiredError(AgentLoopError):
    """Raised when an action requires human approval before proceeding."""

    status_code = status.HTTP_403_FORBIDDEN


# ==============================================================================
# Phase 7 Multi-Agent Orchestration & Controlled Delegation Exceptions
# ==============================================================================


class OrchestrationError(AegisException):
    """Base exception for all Multi-Agent Orchestration errors."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class OrchestrationNotFoundError(OrchestrationError):
    """Raised when a requested orchestration session or task is not found."""

    status_code = status.HTTP_404_NOT_FOUND


class CircularDelegationError(OrchestrationError):
    """Raised when a circular dependency is detected in a delegation plan DAG."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class DelegationPlanError(OrchestrationError):
    """Raised when a delegation plan violates topology, depth, or schema rules."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class WorkerExecutionError(OrchestrationError):
    """Raised when a worker agent loop fails fatally during execution."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class WorkerTimeoutError(OrchestrationError):
    """Raised when a worker exceeds its individual allocated execution timeout."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT


class WorkerBlockedError(OrchestrationError):
    """Raised when a worker is blocked due to unfulfilled required dependencies."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class OrchestrationBudgetExceededError(OrchestrationError):
    """Raised when orchestration-level resource or time limits are breached."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class OrchestrationSafetyStopError(OrchestrationError):
    """Raised when orchestration is halted due to safety policy or constraint violation."""

    status_code = status.HTTP_403_FORBIDDEN


class AggregationError(OrchestrationError):
    """Raised when worker result aggregation or synthesis fails."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


# ==============================================================================
# Safety Gates, Risk Policies & Platform Hardening Exceptions (Phase 8)
# ==============================================================================


class SafetyError(AegisException):
    """Base exception for safety subsystem failures."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class SafetyPolicyViolationError(SafetyError):
    """Raised when an operation violates the platform safety policy."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class RiskAssessmentError(SafetyError):
    """Raised when risk evaluation fails or produces an invalid risk classification."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ApprovalExpiredError(SafetyError):
    """Raised when attempting to execute an approval that has expired."""

    status_code = status.HTTP_410_GONE


class TokenRevokedError(AegisAuthenticationError):
    """Raised when an authentication token has been explicitly revoked."""

    status_code = status.HTTP_401_UNAUTHORIZED


class RateLimitExceededError(SafetyError):
    """Raised when a tenant or IP exceeds safety rate limits."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class SafetyStoppedError(SafetyError):
    """Raised when a task or loop is locked under emergency safety stop."""

    status_code = status.HTTP_403_FORBIDDEN


class CircuitOpenError(SafetyError):
    """Raised when a service or worker circuit breaker is tripped (OPEN)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class AuthorizationDeniedError(AegisAuthorizationError):
    """Raised when an action fails the fine-grained safety authorization gate."""

    status_code = status.HTTP_403_FORBIDDEN


# ==============================================================================
# Phase 9 Dynamic Authorization, RBAC, Token Scopes & Audit Attestation
# ==============================================================================


class AuthorizationError(AegisAuthorizationError):
    """Base exception for RBAC and dynamic policy authorization failures."""

    status_code = status.HTTP_403_FORBIDDEN


class PermissionDeniedError(AuthorizationError):
    """Raised when an authenticated principal lacks the required RBAC permission."""

    status_code = status.HTTP_403_FORBIDDEN


class ScopeRequiredError(AuthorizationError):
    """Raised when an authentication token lacks a required OAuth/token scope."""

    status_code = status.HTTP_403_FORBIDDEN


class PolicyDeniedError(AuthorizationError):
    """Raised when dynamic tenant policy explicitly denies an action."""

    status_code = status.HTTP_403_FORBIDDEN


class RoleAssignmentError(AegisValidationError):
    """Raised when a role assignment violates validation or privilege escalation rules."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class AuditIntegrityError(AegisException):
    """Raised when cryptographic audit chain tampering or verification failure occurs."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers with FastAPI."""

    @app.exception_handler(AegisException)
    async def aegis_exception_handler(request: Request, exc: AegisException) -> JSONResponse:
        status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.warning(
            f"Handled domain exception: {exc.__class__.__name__}: {exc.message}",
            extra={"path": request.url.path, "details": exc.details},
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "type": exc.__class__.__name__,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info(
            f"Request validation failed on {request.url.path}",
            extra={"errors": exc.errors()},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "type": "RequestValidationError",
                    "message": "Invalid request parameters or payload.",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled server error at {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "type": "InternalServerError",
                    "message": "An unexpected error occurred. Please contact the administrator.",
                    "details": {},
                }
            },
        )
