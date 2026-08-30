"""Telemetry schema for tracking agent and LLM execution metrics."""

from datetime import datetime

from app.schemas.common import AegisBaseSchema


class TelemetryData(AegisBaseSchema):
    """
    Execution telemetry metrics.
    Only captures real metrics returned by providers; missing metrics remain None.
    """

    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: float | None = None
    provider: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
