"""
AgentX – Portfolio Health Monitor
Centralized OpenRouter LLM Service
"""

import asyncio
from dataclasses import dataclass
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from langsmith import traceable
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings, get_settings

logger = logging.getLogger("agentx.services.llm")

T = TypeVar("T", bound=BaseModel)


# ------------------------------------------------------------------------------
# Custom Exceptions (Never expose API keys or credentials in error messages)
# ------------------------------------------------------------------------------
class LLMError(Exception):
    """Base exception for all LLM service failures."""
    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is missing or invalid."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised on HTTP 401 or 403 authentication failures."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limits (HTTP 429) persist after bounded retries."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM requests exceed the configured timeout."""
    pass


class LLMProviderError(LLMError):
    """Raised on upstream provider errors (HTTP 5xx) or network failures."""
    pass


class LLMValidationError(LLMError):
    """Raised when LLM structured output fails Pydantic schema validation."""
    pass


# ------------------------------------------------------------------------------
# Response Data Containers
# ------------------------------------------------------------------------------
class LLMUsage(BaseModel):
    """Token usage metrics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """Standardized response from OpenRouter chat completion."""
    content: str
    model: str
    role: str = "assistant"
    finish_reason: Optional[str] = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: float = 0.0


# ------------------------------------------------------------------------------
# Centralized OpenRouter Service
# ------------------------------------------------------------------------------
class LLMService:
    """
    Centralized asynchronous LLM gateway utilizing OpenRouter's OpenAI-compatible API.
    Provides:
      - Configurable model routing
      - Automatic retries with exponential backoff & jitter
      - Seamless model fallback upon provider outage
      - Structured output generation and Pydantic validation
      - Safe logging with complete API key masking
    """

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 520, 521, 522, 524}

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._external_client = client
        self._internal_client: Optional[httpx.AsyncClient] = None

        self.base_url = self.settings.OPENROUTER_BASE_URL.rstrip("/")
        self.default_model = self.settings.OPENROUTER_DEFAULT_MODEL
        self.fallback_model = self.settings.OPENROUTER_FALLBACK_MODEL
        self.default_temperature = self.settings.LLM_TEMPERATURE
        self.max_retries = self.settings.LLM_MAX_RETRIES
        self.timeout_seconds = self.settings.LLM_TIMEOUT_SECONDS

    async def _get_client(self) -> httpx.AsyncClient:
        """Retrieve existing client or instantiate managed AsyncClient."""
        if self._external_client is not None:
            return self._external_client
        if self._internal_client is None or self._internal_client.is_closed:
            self._internal_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
            )
        return self._internal_client

    async def close(self) -> None:
        """Close managed internal HTTP client session."""
        if self._internal_client and not self._internal_client.is_closed:
            await self._internal_client.aclose()
            self._internal_client = None

    def _get_headers(self) -> Dict[str, str]:
        """Construct OpenRouter headers; never exposes raw key in exceptions."""
        if not self.settings.OPENROUTER_API_KEY:
            raise LLMConfigurationError(
                "OPENROUTER_API_KEY is not configured in application settings."
            )
        api_key = self.settings.OPENROUTER_API_KEY.get_secret_value()
        if not api_key:
            raise LLMConfigurationError(
                "OPENROUTER_API_KEY contains an empty value."
            )

        return {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/agentx/portfolio-health",
            "X-Title": "AgentX - Portfolio Health Monitor",
            "Content-Type": "application/json",
        }

    async def _execute_with_retry(
        self,
        payload: Dict[str, Any],
        model: str,
        attempt_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes an HTTP request to OpenRouter with bounded exponential backoff
        and optional model fallback upon transient failure.
        """
        client = await self._get_client()
        headers = self._get_headers()
        url = f"{self.base_url}/chat/completions"

        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            start_time = time.perf_counter()
            try:
                logger.debug(
                    "Dispatching LLM request | model=%s | attempt=%d/%d",
                    model,
                    attempt + 1,
                    self.max_retries + 1,
                )
                response = await client.post(url, json=payload, headers=headers)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                # Successful completion
                if response.status_code == 200:
                    data = response.json()
                    data["_latency_ms"] = latency_ms
                    return data

                # Client authentication failures (non-retryable)
                if response.status_code in (401, 403):
                    logger.error(
                        "OpenRouter authentication rejected | status=%d",
                        response.status_code,
                    )
                    raise LLMAuthenticationError(
                        f"Authentication failed with OpenRouter gateway (HTTP {response.status_code})."
                    )

                # Rate limits or provider failures
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    is_rate_limit = response.status_code == 429
                    err_msg = (
                        f"Rate limit exceeded (HTTP 429)"
                        if is_rate_limit
                        else f"Upstream provider failure (HTTP {response.status_code})"
                    )

                    if attempt < self.max_retries:
                        # Determine wait duration, honoring Retry-After if provided
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            backoff = min(float(retry_after), 30.0)
                        else:
                            backoff = (2 ** attempt) + random.uniform(0.1, 0.5)

                        logger.warning(
                            "%s on model '%s'. Backing off for %.2fs (attempt %d/%d)",
                            err_msg,
                            model,
                            backoff,
                            attempt + 1,
                            self.max_retries,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        if is_rate_limit:
                            last_exception = LLMRateLimitError(
                                f"Rate limit on model '{model}' exhausted after {self.max_retries} retries."
                            )
                        else:
                            last_exception = LLMProviderError(
                                f"Provider failure on model '{model}' (HTTP {response.status_code})."
                            )
                        break

                # Other HTTP 4xx errors (non-retryable client error)
                response_snippet = response.text[:200]
                logger.error(
                    "OpenRouter rejected request | status=%d | detail=%s",
                    response.status_code,
                    response_snippet,
                )
                raise LLMError(
                    f"OpenRouter returned HTTP {response.status_code}: {response_snippet}"
                )

            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                last_exception = LLMTimeoutError(
                    f"LLM request timed out after {self.timeout_seconds}s for model '{model}'."
                )
                if attempt < self.max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning(
                        "Timeout on model '%s' (%.2fms). Retrying in %.2fs...",
                        model,
                        latency_ms,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                break

            except httpx.NetworkError as exc:
                last_exception = LLMProviderError(f"Network error communicating with OpenRouter: {exc}")
                if attempt < self.max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning(
                        "Network error on model '%s'. Retrying in %.2fs...",
                        model,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                break

        # Attempt failover to fallback model if primary model fails
        if attempt_fallback and model != self.fallback_model and self.fallback_model:
            logger.warning(
                "Primary model '%s' failed (%s). Failing over to fallback model '%s'...",
                model,
                last_exception,
                self.fallback_model,
            )
            fallback_payload = dict(payload)
            fallback_payload["model"] = self.fallback_model
            return await self._execute_with_retry(
                payload=fallback_payload,
                model=self.fallback_model,
                attempt_fallback=False,
            )

        if last_exception:
            raise last_exception
        raise LLMError(f"LLM request failed for model '{model}'.")

    # --------------------------------------------------------------------------
    # Public Completion API
    # --------------------------------------------------------------------------
    @traceable(name="OpenRouter Chat Completion", run_type="llm")
    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send an asynchronous chat completion request to OpenRouter.

        Args:
            messages: List of chat messages (e.g. [{"role": "user", "content": "..."}]).
            model: Target model identifier. Defaults to configured OPENROUTER_DEFAULT_MODEL.
            temperature: Sampling temperature (0.0 to 2.0). Defaults to LLM_TEMPERATURE.
            max_tokens: Optional token generation upper bound.
            response_format: Optional format dict (e.g., {"type": "json_object"}).
            **kwargs: Extra parameters passed to the OpenRouter payload.

        Returns:
            LLMResponse object containing text content, usage, and latency.
        """
        chosen_model = model or self.default_model
        chosen_temp = temperature if temperature is not None else self.default_temperature

        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": chosen_temp,
            **kwargs,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format

        data = await self._execute_with_retry(payload, model=chosen_model)

        choices = data.get("choices", [])
        if not choices:
            raise LLMError("OpenRouter response did not contain any completion choices.")

        first_choice = choices[0]
        message = first_choice.get("message", {})
        content = message.get("content", "") or ""
        finish_reason = first_choice.get("finish_reason")
        resolved_model = data.get("model", chosen_model)
        latency_ms = data.get("_latency_ms", 0.0)

        usage_data = data.get("usage", {})
        usage = LLMUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(
            content=content,
            model=resolved_model,
            role=message.get("role", "assistant"),
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> str:
        """
        Convenience method to generate a plain string response from a user prompt.
        """
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.generate_text(
            messages=messages,
            model=model,
            temperature=temperature,
            **kwargs,
        )
        return response.content

    @traceable(name="OpenRouter Structured Output", run_type="llm")
    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_validation_retries: int = 2,
        **kwargs: Any,
    ) -> T:
        """
        Generates a response and validates it against a target Pydantic schema.
        Automatically instructs the model to return valid JSON adhering to the schema.

        Args:
            messages: List of chat messages.
            response_model: Pydantic model class defining the expected response schema.
            model: Target model identifier.
            temperature: Sampling temperature (recommended <= 0.2 for structured output).
            max_validation_retries: Number of correction retries if JSON or validation fails.
            **kwargs: Extra arguments for the chat completion.

        Returns:
            An instance of response_model populated with validated data.
        """
        json_schema = json.dumps(response_model.model_json_schema(), indent=2)

        schema_directive = (
            f"\n\nCRITICAL REQUIREMENT: You must respond ONLY with a valid JSON object matching "
            f"this JSON schema:\n{json_schema}\n"
            f"Do not include any Markdown code blocks, backticks, or explanatory preamble."
        )

        # Clone messages to prevent mutating caller inputs
        augmented_messages = [dict(m) for m in messages]
        if augmented_messages and augmented_messages[0]["role"] == "system":
            augmented_messages[0]["content"] += schema_directive
        else:
            augmented_messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"You are a precise financial analysis assistant.{schema_directive}",
                },
            )

        chosen_temp = temperature if temperature is not None else min(self.default_temperature, 0.2)

        last_raw_content: str = ""
        last_error_detail: str = ""

        for val_attempt in range(max_validation_retries + 1):
            response = await self.generate_text(
                messages=augmented_messages,
                model=model,
                temperature=chosen_temp,
                response_format={"type": "json_object"},
                **kwargs,
            )
            raw = response.content.strip()
            last_raw_content = raw

            # Strip markdown fences if present
            cleaned = raw
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                parsed_json = json.loads(cleaned)
                return response_model.model_validate(parsed_json)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error_detail = str(exc)
                logger.warning(
                    "Structured output validation failed (attempt %d/%d): %s",
                    val_attempt + 1,
                    max_validation_retries + 1,
                    last_error_detail,
                )
                if val_attempt < max_validation_retries:
                    # Provide targeted correction feedback for subsequent attempt
                    augmented_messages.append({"role": "assistant", "content": raw})
                    augmented_messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your previous response could not be parsed: {last_error_detail}\n"
                                f"Please fix the syntax and output ONLY raw valid JSON matching the schema."
                            ),
                        }
                    )
                    continue

        raise LLMValidationError(
            f"Failed to validate LLM output against schema '{response_model.__name__}'. "
            f"Error: {last_error_detail} | Raw Content Snippet: {last_raw_content[:300]}"
        )


# ------------------------------------------------------------------------------
# Dependency / Singleton Access
# ------------------------------------------------------------------------------
_global_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return application-wide shared LLMService singleton."""
    global _global_llm_service
    if _global_llm_service is None:
        _global_llm_service = LLMService()
    return _global_llm_service

