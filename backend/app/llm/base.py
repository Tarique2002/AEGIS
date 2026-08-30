"""Base abstractions and data structures for LLM Providers."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.schemas.common import AegisBaseSchema, ChatMessage

T = TypeVar("T", bound=BaseModel)


class ProviderMetadata(AegisBaseSchema):
    """Metadata describing a configured LLM provider and model."""

    provider_name: str
    model_name: str
    is_local: bool = False
    supports_structured_output: bool = True
    context_window: int | None = None


class LLMResponse(AegisBaseSchema):
    """Raw text response from an LLM call along with token telemetry."""

    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: float | None = None
    model: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class StructuredLLMResponse(AegisBaseSchema, Generic[T]):
    """Structured, typed response containing a validated Pydantic model."""

    data: T
    raw_text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: float | None = None
    model: str | None = None


class LLMProvider(ABC):
    """
    Abstract interface for LLM Providers.
    Decouples agent business logic from specific vendors (Ollama, OpenAI, Anthropic, Gemini).
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a raw text completion from a list of chat messages."""
        ...

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[ChatMessage],
        response_model: type[T],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> StructuredLLMResponse[T]:
        """Generate structured output validated against a Pydantic model."""
        ...

    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """Return provider and model metadata."""
        ...
