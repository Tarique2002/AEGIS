"""Policy constraints, safety bounds, and budget limits for Multi-Agent Orchestration."""

from pydantic import Field

from app.schemas.common import AegisBaseSchema


class OrchestrationPolicy(AegisBaseSchema):
    """
    Configurable safety policy governing multi-agent task delegation and resource consumption.
    """

    max_workers: int = Field(default=6, ge=1, le=10)
    max_parallel_workers: int = Field(default=3, ge=1, le=5)
    max_total_iterations: int = Field(default=20, ge=1, le=50)
    max_total_tool_calls: int = Field(default=60, ge=1, le=150)
    max_total_llm_calls: int = Field(default=40, ge=1, le=100)
    max_total_retries: int = Field(default=15, ge=0, le=30)
    max_total_execution_seconds: float = Field(default=900.0, ge=0.1, le=3600.0)
    max_dependency_depth: int = Field(default=5, ge=1, le=10)
    max_rework_rounds: int = Field(default=2, ge=0, le=5)
    default_worker_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    completion_score_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
