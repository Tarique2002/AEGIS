"""Ollama LLM Provider implementation using async HTTP requests."""

import json
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.errors import LLMProviderError, LLMTimeoutError, ModelResponseValidationError
from app.llm.base import LLMProvider, LLMResponse, ProviderMetadata, StructuredLLMResponse
from app.schemas.common import ChatMessage

T = TypeVar("T", bound=BaseModel)


class OllamaProvider(LLMProvider):
    """
    Ollama LLM provider using Ollama's local HTTP REST API.
    Compatible with any locally pulled Ollama model.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.LLM_MODEL
        self.timeout_seconds = timeout_seconds or settings.LLM_TIMEOUT_SECONDS

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name="ollama",
            model_name=self.model_name,
            is_local=True,
            supports_structured_output=True,
        )

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        formatted = []
        for msg in messages:
            role_str = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            formatted.append({"role": role_str, "content": msg.content})
        return formatted

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Ollama request to {url} timed out after {self.timeout_seconds}s.",
                details={"model": self.model_name},
            ) from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise LLMProviderError(
                f"Ollama provider error: {str(exc)}",
                details={"model": self.model_name, "base_url": self.base_url},
            ) from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        message_content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")
        total_tokens = (
            (prompt_tokens + completion_tokens)
            if (prompt_tokens is not None and completion_tokens is not None)
            else None
        )

        return LLMResponse(
            content=message_content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            model=self.model_name,
            raw=data,
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
        url = f"{self.base_url}/api/chat"

        # Append schema instruction to messages
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        system_instruction = (
            "You MUST respond ONLY with a valid JSON object matching this schema:\n"
            f"{schema_json}"
        )

        augmented_messages = [
            ChatMessage(role="system", content=system_instruction),  # type: ignore[arg-type]
            *messages,
        ]

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._format_messages(augmented_messages),
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Ollama request to {url} timed out after {self.timeout_seconds}s.",
                details={"model": self.model_name},
            ) from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise LLMProviderError(
                f"Ollama provider error: {str(exc)}",
                details={"model": self.model_name, "base_url": self.base_url},
            ) from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        raw_text = data.get("message", {}).get("content", "")

        try:
            validated_obj = response_model.model_validate_json(raw_text)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ModelResponseValidationError(
                f"Failed to validate LLM response against {response_model.__name__}.",
                details={"raw_response": raw_text, "model": self.model_name},
            ) from exc

        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")
        total_tokens = (
            (prompt_tokens + completion_tokens)
            if (prompt_tokens is not None and completion_tokens is not None)
            else None
        )

        return StructuredLLMResponse[T](
            data=validated_obj,
            raw_text=raw_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            model=self.model_name,
        )
