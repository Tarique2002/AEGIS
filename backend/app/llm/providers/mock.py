"""Mock LLM Provider for deterministic testing and offline operation."""

import asyncio
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.errors import LLMProviderError, LLMTimeoutError, ModelResponseValidationError
from app.llm.base import LLMProvider, LLMResponse, ProviderMetadata, StructuredLLMResponse
from app.schemas.common import ChatMessage

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    """
    Configurable Mock LLM Provider for tests and offline development.
    No API keys, network access, or external services required.
    """

    def __init__(
        self,
        *,
        model_name: str = "mock-model-v1",
        default_response_text: str = "This is a deterministic mock response from AEGIS.",
        should_fail: bool = False,
        failure_message: str = "Simulated upstream provider failure",
        should_timeout: bool = False,
        timeout_seconds: float = 0.01,
        malformed_json: bool = False,
        prompt_tokens: int = 42,
        completion_tokens: int = 18,
    ) -> None:
        self.model_name = model_name
        self.default_response_text = default_response_text
        self.should_fail = should_fail
        self.failure_message = failure_message
        self.should_timeout = should_timeout
        self.timeout_seconds = timeout_seconds
        self.malformed_json = malformed_json
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.call_count = 0
        self.recorded_messages: list[list[ChatMessage]] = []

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name="mock",
            model_name=self.model_name,
            is_local=True,
            supports_structured_output=True,
            context_window=8192,
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.call_count += 1
        self.recorded_messages.append(messages)

        if self.should_timeout:
            await asyncio.sleep(self.timeout_seconds)
            raise LLMTimeoutError(
                f"Call to provider 'mock' with model '{self.model_name}' timed out."
            )

        if self.should_fail:
            raise LLMProviderError(self.failure_message)

        return LLMResponse(
            content=self.default_response_text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.prompt_tokens + self.completion_tokens,
            duration_ms=12.5,
            model=self.model_name,
            raw={"mock": True},
        )

    async def generate_structured(
        self,
        messages: list[ChatMessage],
        response_model: type[T],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> StructuredLLMResponse[T]:
        self.call_count += 1
        self.recorded_messages.append(messages)

        if self.should_timeout:
            await asyncio.sleep(self.timeout_seconds)
            raise LLMTimeoutError(
                f"Call to provider 'mock' with model '{self.model_name}' timed out."
            )

        if self.should_fail:
            raise LLMProviderError(self.failure_message)

        if self.malformed_json:
            raw_invalid = "This is not valid JSON at all {"
            raise ModelResponseValidationError(
                "Failed to parse structured output from model.",
                details={"raw_response": raw_invalid, "target_schema": response_model.__name__},
            )

        # Attempt to construct default fields matching target response_model
        # For standard AgentResponseModel, supply default response_text
        try:
            sample_data: dict[str, Any] = {
                "response_text": self.default_response_text,
                "is_completed": True,
                "next_action": None,
                "confidence": 1.0,
                "metadata": {"mock": True},
            }
            validated_obj = response_model.model_validate(sample_data)
            raw_text = validated_obj.model_dump_json()
        except ValidationError as e:
            # Fallback to model instantiation if different schema
            raise ModelResponseValidationError(
                f"Mock structured generation could not satisfy schema {response_model.__name__}",
                details={"errors": e.errors()},
            ) from e

        return StructuredLLMResponse[T](
            data=validated_obj,
            raw_text=raw_text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.prompt_tokens + self.completion_tokens,
            duration_ms=15.0,
            model=self.model_name,
        )
