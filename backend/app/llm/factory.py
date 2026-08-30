"""Factory for resolving and instantiating configured LLM Providers."""

from typing import Any

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.providers.mock import MockLLMProvider
from app.llm.providers.ollama import OllamaProvider


def get_llm_provider(
    provider_name: str | None = None,
    **kwargs: Any,
) -> LLMProvider:
    """
    Resolve and return an LLMProvider instance based on configuration or explicit parameter.
    """
    provider = (provider_name or settings.LLM_PROVIDER).lower().strip()

    if provider == "mock":
        return MockLLMProvider(**kwargs)
    elif provider == "ollama":
        return OllamaProvider(**kwargs)
    else:
        # Default fallback for testing or unrecognized providers
        return MockLLMProvider(**kwargs)
