"""Centralized governance policies and execution bounds for autonomous agent loops."""

from pydantic import Field

from app.agent_loop.schemas import AutonomyLevel
from app.schemas.common import AegisBaseSchema


class AgentLoopPolicy(AegisBaseSchema):
    """
    Configurable limits enforcing strict bounds on iteration count, latency,
    tool calls, LLM usage, retries, and memory operations within an agent loop.
    """

    max_iterations: int = Field(default=8, ge=1, le=20)
    max_total_execution_seconds: float = Field(default=600.0, ge=0.1, le=3600.0)
    max_tool_calls: int = Field(default=30, ge=1, le=100)
    max_llm_calls: int = Field(default=20, ge=1, le=50)
    max_plan_executions: int = Field(default=8, ge=1, le=20)
    max_total_retries: int = Field(default=10, ge=0, le=30)
    max_memory_retrievals: int = Field(default=20, ge=0, le=50)
    max_memory_writes: int = Field(default=10, ge=0, le=30)
    max_stagnant_iterations: int = Field(default=2, ge=1, le=5)
    completion_score_threshold: float = Field(default=0.85, ge=0.5, le=1.0)
    max_observation_chars: int = Field(default=10000, ge=1000, le=50000)
    default_autonomy_level: AutonomyLevel = AutonomyLevel.BOUNDED
