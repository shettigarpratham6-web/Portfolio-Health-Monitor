"""
AgentX – Portfolio Health Monitor
Unit Tests for Centralized OpenRouter LLM Service
Uses Mocked HTTP Responses (No paid API calls)
"""

import json
from typing import Any, Dict
import unittest.mock as mock

import httpx
import pytest
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.services.llm import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMService,
    LLMTimeoutError,
    LLMValidationError,
)


# Test schema for structured output validation
class CompanyAnalysis(BaseModel):
    ticker: str
    sentiment: str = Field(description="BULLISH, BEARISH, or NEUTRAL")
    risk_score: int = Field(ge=0, le=100)
    summary: str


def make_mock_openrouter_response(
    content: str,
    model: str = "anthropic/claude-3.5-sonnet",
    status_code: int = 200,
    headers: Dict[str, str] = None,
) -> httpx.Response:
    """Generate mock httpx.Response simulating OpenRouter API."""
    body = {
        "id": "gen-mock-12345",
        "model": model,
        "object": "chat.completion",
        "created": 1700000000,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 18,
            "total_tokens": 60,
        },
    }
    return httpx.Response(
        status_code=status_code,
        json=body,
        headers=headers or {"content-type": "application/json"},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


@pytest.fixture
def mock_settings():
    """Isolated settings fixture with test credentials and minimal retry delays."""
    return Settings(
        secret_key="test-secret-key-32chars-minimum-length-ok",
        openrouter_api_key="sk-or-v1-mock-test-key-never-exposed",
        openrouter_default_model="anthropic/claude-3.5-sonnet",
        openrouter_fallback_model="openai/gpt-4o-mini",
        llm_temperature=0.1,
        llm_max_retries=2,
        llm_timeout_seconds=5.0,
    )


# ------------------------------------------------------------------------------
# Test 1: Successful Text Generation & Header Construction
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_successful_text_generation(mock_settings):
    mock_transport = mock.AsyncMock()
    mock_transport.post.return_value = make_mock_openrouter_response(
        content="Apple's balance sheet remains exceptionally strong.",
        model="anthropic/claude-3.5-sonnet",
    )

    service = LLMService(settings=mock_settings, client=mock_transport)

    messages = [{"role": "user", "content": "Analyze AAPL balance sheet."}]
    response = await service.generate_text(messages)

    assert isinstance(response, LLMResponse)
    assert response.content == "Apple's balance sheet remains exceptionally strong."
    assert response.model == "anthropic/claude-3.5-sonnet"
    assert response.usage.total_tokens == 60
    assert response.finish_reason == "stop"

    # Verify OpenRouter headers sent
    mock_transport.post.assert_called_once()
    call_kwargs = mock_transport.post.call_args[1]
    headers = call_kwargs["headers"]
    assert "Authorization" in headers
    assert "Bearer sk-or-v1-mock-test-key-never-exposed" in headers["Authorization"]
    assert headers["HTTP-Referer"] == "https://github.com/agentx/portfolio-health"
    assert headers["X-Title"] == "AgentX - Portfolio Health Monitor"


# ------------------------------------------------------------------------------
# Test 2: Configurable Model Selection
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_custom_model_selection(mock_settings):
    mock_transport = mock.AsyncMock()
    mock_transport.post.return_value = make_mock_openrouter_response(
        content="Analysis using custom model.",
        model="meta-llama/llama-3.3-70b-instruct",
    )

    service = LLMService(settings=mock_settings, client=mock_transport)

    messages = [{"role": "user", "content": "Quick check."}]
    response = await service.generate_text(
        messages, model="meta-llama/llama-3.3-70b-instruct"
    )

    assert response.model == "meta-llama/llama-3.3-70b-instruct"
    call_payload = mock_transport.post.call_args[1]["json"]
    assert call_payload["model"] == "meta-llama/llama-3.3-70b-instruct"


# ------------------------------------------------------------------------------
# Test 3: Rate Limiting (HTTP 429) with Retry & Backoff
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_rate_limit_retry_success(mock_settings):
    rate_limit_resp = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        headers={"Retry-After": "0.01"},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    success_resp = make_mock_openrouter_response("Success after rate limit retry.")

    mock_transport = mock.AsyncMock()
    mock_transport.post.side_effect = [rate_limit_resp, success_resp]

    service = LLMService(settings=mock_settings, client=mock_transport)

    # Patch sleep to keep tests fast
    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as mock_sleep:
        response = await service.generate_text([{"role": "user", "content": "Hi"}])
        assert response.content == "Success after rate limit retry."
        assert mock_transport.post.call_count == 2
        mock_sleep.assert_called_once()


# ------------------------------------------------------------------------------
# Test 4: Rate Limit Exhaustion
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_rate_limit_exhaustion_triggers_fallback_or_error(mock_settings):
    rate_limit_resp = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    mock_transport = mock.AsyncMock()
    # Fails both primary model and fallback model
    mock_transport.post.return_value = rate_limit_resp

    service = LLMService(settings=mock_settings, client=mock_transport)

    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        with pytest.raises(LLMRateLimitError):
            await service.generate_text([{"role": "user", "content": "Hi"}])


# ------------------------------------------------------------------------------
# Test 5: Provider Failure (HTTP 502) Triggers Automatic Model Fallback
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_automatic_fallback_on_provider_outage(mock_settings):
    outage_resp = httpx.Response(
        status_code=502,
        text="Bad Gateway from Claude upstream",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    fallback_success = make_mock_openrouter_response(
        content="Response from fallback GPT-4o-mini.",
        model="openai/gpt-4o-mini",
    )

    mock_transport = mock.AsyncMock()
    # Primary model fails max_retries + 1 times (3 times), then fallback succeeds on 1st try
    mock_transport.post.side_effect = [
        outage_resp,
        outage_resp,
        outage_resp,
        fallback_success,
    ]

    service = LLMService(settings=mock_settings, client=mock_transport)

    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        response = await service.generate_text(
            [{"role": "user", "content": "Analyze risks."}]
        )
        assert response.content == "Response from fallback GPT-4o-mini."
        assert response.model == "openai/gpt-4o-mini"
        # 3 calls on primary + 1 call on fallback
        assert mock_transport.post.call_count == 4


# ------------------------------------------------------------------------------
# Test 6: Request Timeout Handling
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_request_timeout_handling(mock_settings):
    mock_transport = mock.AsyncMock()
    mock_transport.post.side_effect = httpx.ReadTimeout("Read timed out")

    service = LLMService(settings=mock_settings, client=mock_transport)

    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        with pytest.raises(LLMTimeoutError):
            await service.generate_text([{"role": "user", "content": "Wait"}])


# ------------------------------------------------------------------------------
# Test 7: Structured Output Validation with Pydantic Schema
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_structured_output_validation(mock_settings):
    valid_json_payload = json.dumps(
        {
            "ticker": "NVDA",
            "sentiment": "BULLISH",
            "risk_score": 35,
            "summary": "Solid growth supported by hyperscaler capital expenditure.",
        }
    )

    mock_transport = mock.AsyncMock()
    mock_transport.post.return_value = make_mock_openrouter_response(
        content=valid_json_payload
    )

    service = LLMService(settings=mock_settings, client=mock_transport)

    messages = [{"role": "user", "content": "Evaluate NVDA."}]
    result = await service.generate_structured(
        messages=messages,
        response_model=CompanyAnalysis,
    )

    assert isinstance(result, CompanyAnalysis)
    assert result.ticker == "NVDA"
    assert result.sentiment == "BULLISH"
    assert result.risk_score == 35
    assert "hyperscaler" in result.summary


# ------------------------------------------------------------------------------
# Test 8: Structured Output Self-Correction
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_structured_output_self_correction(mock_settings):
    # First response: Invalid JSON / schema missing fields
    invalid_content = "Here is the data: {ticker: NVDA, risk: high}"
    # Second response: Valid JSON adhering to schema
    valid_json = json.dumps(
        {
            "ticker": "NVDA",
            "sentiment": "BULLISH",
            "risk_score": 40,
            "summary": "Recovered valid json payload.",
        }
    )

    resp_1 = make_mock_openrouter_response(content=invalid_content)
    resp_2 = make_mock_openrouter_response(content=valid_json)

    mock_transport = mock.AsyncMock()
    mock_transport.post.side_effect = [resp_1, resp_2]

    service = LLMService(settings=mock_settings, client=mock_transport)

    result = await service.generate_structured(
        messages=[{"role": "user", "content": "Score NVDA."}],
        response_model=CompanyAnalysis,
        max_validation_retries=2,
    )

    assert isinstance(result, CompanyAnalysis)
    assert result.ticker == "NVDA"
    assert result.risk_score == 40
    assert mock_transport.post.call_count == 2


# ------------------------------------------------------------------------------
# Test 9: Security – API Keys Never Exposed in Exceptions
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_api_key_not_exposed_on_auth_failure(mock_settings):
    auth_err_resp = httpx.Response(
        status_code=401,
        text="Unauthorized: Invalid API Key",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    mock_transport = mock.AsyncMock()
    mock_transport.post.return_value = auth_err_resp

    service = LLMService(settings=mock_settings, client=mock_transport)

    with pytest.raises(LLMAuthenticationError) as exc_info:
        await service.generate_text([{"role": "user", "content": "Test key."}])

    raw_key = mock_settings.OPENROUTER_API_KEY.get_secret_value()
    # Confirm secret key is NEVER printed in exception message
    assert raw_key not in str(exc_info.value)
    assert "Authentication failed" in str(exc_info.value)

