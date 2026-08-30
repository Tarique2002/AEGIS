"""Structured model response schemas."""

from typing import Any

from pydantic import Field

from app.schemas.common import AegisBaseSchema


class AgentResponseModel(AegisBaseSchema):
    """
    Standard structured response output returned by the LLM in Phase 1 runtime.
    Decoupled from specific vendor formatting.
    """

    response_text: str = Field(..., description="Main synthesized textual response or explanation")
    is_completed: bool = Field(
        default=True, description="Indicates whether the task objective is complete"
    )
    next_action: str | None = Field(
        default=None, description="Optional metadata describing recommended next step if incomplete"
    )
    confidence: float | None = Field(
        default=None, description="Confidence score for the response between 0.0 and 1.0"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary metadata from LLM output"
    )
