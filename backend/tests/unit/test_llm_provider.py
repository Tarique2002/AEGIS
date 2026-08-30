"""Unit tests for LLM Provider abstraction, mock provider, and error handling."""

import pytest
from app.core.errors import LLMProviderError, LLMTimeoutError, ModelResponseValidationError
from app.llm.base import LLMResponse, StructuredLLMResponse
from app.llm.factory import get_llm_provider
from app.llm.providers.mock import MockLLMProvider
from app.llm.providers.ollama import OllamaProvider
from app.schemas.common import ChatMessage, ChatRole
from app.schemas.response import AgentResponseModel


@pytest.mark.asyncio
async def test_mock_llm_provider_raw_generate():
    provider = MockLLMProvider(
        model_name="test-model",
        default_response_text="Custom mock output",
        prompt_tokens=50,
        completion_tokens=25,
    )
    messages = [
        ChatMessage(role=ChatRole.USER, content="Hello AEGIS"),
    ]
    response: LLMResponse = await provider.generate(messages)

    assert response.content == "Custom mock output"
    assert response.prompt_tokens == 50
    assert response.completion_tokens == 25
    assert response.total_tokens == 75
    assert response.model == "test-model"
    assert provider.call_count == 1
    assert len(provider.recorded_messages) == 1


@pytest.mark.asyncio
async def test_mock_llm_provider_structured_generate():
    provider = MockLLMProvider(
        default_response_text="Structured PostgreSQL explanation",
    )
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content="You are AEGIS"),
        ChatMessage(role=ChatRole.USER, content="Explain indexing"),
    ]
    response: StructuredLLMResponse[AgentResponseModel] = await provider.generate_structured(
        messages=messages,
        response_model=AgentResponseModel,
    )

    assert isinstance(response.data, AgentResponseModel)
    assert response.data.response_text == "Structured PostgreSQL explanation"
    assert response.data.is_completed is True
    assert response.prompt_tokens is not None
    assert response.completion_tokens is not None


@pytest.mark.asyncio
async def test_mock_llm_provider_timeout_error():
    provider = MockLLMProvider(should_timeout=True, timeout_seconds=0.001)
    messages = [ChatMessage(role=ChatRole.USER, content="Timeout test")]

    with pytest.raises(LLMTimeoutError) as exc_info:
        await provider.generate(messages)

    assert "timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mock_llm_provider_failure_error():
    provider = MockLLMProvider(should_fail=True, failure_message="Upstream API 500 error")
    messages = [ChatMessage(role=ChatRole.USER, content="Failure test")]

    with pytest.raises(LLMProviderError) as exc_info:
        await provider.generate_structured(messages, AgentResponseModel)

    assert "Upstream API 500 error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mock_llm_provider_malformed_json():
    provider = MockLLMProvider(malformed_json=True)
    messages = [ChatMessage(role=ChatRole.USER, content="Malformed test")]

    with pytest.raises(ModelResponseValidationError) as exc_info:
        await provider.generate_structured(messages, AgentResponseModel)

    assert "Failed to parse structured output" in str(exc_info.value)


def test_provider_factory_resolution():
    mock_p = get_llm_provider("mock")
    assert isinstance(mock_p, MockLLMProvider)
    assert mock_p.metadata().provider_name == "mock"

    ollama_p = get_llm_provider("ollama")
    assert isinstance(ollama_p, OllamaProvider)
    assert ollama_p.metadata().provider_name == "ollama"

    default_p = get_llm_provider("unrecognized-custom-provider")
    assert isinstance(default_p, MockLLMProvider)
