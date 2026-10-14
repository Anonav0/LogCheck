"""Provider abstraction and factory for LLM backends."""

import json
import time
from collections.abc import Callable

import requests

from app.core.config import Settings, get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)

# Standard default mock response adheres strictly to AIAnalysis schema
_DEFAULT_MOCK_RESPONSE = json.dumps(
    {
        "summary": "Mock analysis: Primary database connection pool saturation identified as main root cause.",
        "likely_causes": [
            {
                "description": "Database connection exhaustion under high concurrency.",
                "reasoning": "Connection timeout tracebacks show workers failing to acquire connections from the pool.",
                "evidence_refs": [
                    {
                        "line_number": 8,
                        "excerpt": "DatabaseConnectionError: Connection lost to database cluster primary",
                    }
                ],
            }
        ],
        "recommended_actions": [
            {
                "action": "Increase max_connections parameter in database pool configuration.",
                "rationale": "Prevents queue starvation during burst traffic.",
                "priority": "high",
                "evidence_refs": [
                    {
                        "line_number": 8,
                        "excerpt": "DatabaseConnectionError: Connection lost to database cluster primary",
                    }
                ],
            }
        ],
        "confidence": 0.9,
        "limitations": [
            "Mock test response; external network latency and database metrics were unobserved."
        ],
        "evidence_refs": [
            {
                "line_number": 8,
                "excerpt": "DatabaseConnectionError: Connection lost to database cluster primary",
            }
        ],
    }
)


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for offline unit and integration tests."""

    def __init__(
        self,
        response_text: str | None = None,
        response_generator: Callable[[str], str] | None = None,
        simulated_delay: float = 0.0,
        simulated_exception: Exception | None = None,
        model_name: str = "mock-gpt-4o",
    ) -> None:
        self._response_text = (
            response_text if response_text is not None else _DEFAULT_MOCK_RESPONSE
        )
        self._response_generator = response_generator
        self._simulated_delay = simulated_delay
        self._simulated_exception = simulated_exception
        self._model_name = model_name
        self.call_count = 0
        self.last_prompt: str | None = None

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str | None:
        return self._model_name

    def set_response(self, text: str) -> None:
        """Update mock response text."""
        self._response_text = text

    def set_exception(self, exc: Exception | None) -> None:
        """Set an exception to raise upon generate call."""
        self._simulated_exception = exc

    def generate(self, prompt: str, timeout_seconds: float | None = None) -> str:
        """Return the mocked response or trigger simulated behavior."""
        self.call_count += 1
        self.last_prompt = prompt

        if self._simulated_delay > 0:
            if timeout_seconds is not None and self._simulated_delay > timeout_seconds:
                time.sleep(timeout_seconds)
                raise LLMTimeoutError(
                    f"Mock request timed out after {timeout_seconds}s.",
                    timeout_seconds=timeout_seconds,
                    provider="mock",
                )
            time.sleep(self._simulated_delay)

        if self._simulated_exception is not None:
            raise self._simulated_exception

        if self._response_generator is not None:
            return self._response_generator(prompt)

        return self._response_text


class OpenAIProvider(LLMProvider):
    """Production provider adapter communicating with OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        max_output_tokens: int = 1200,
    ) -> None:
        if not api_key:
            raise LLMAuthenticationError(
                "OpenAI API key is missing or empty. Please set LLM_API_KEY.",
                provider="openai",
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_output_tokens = max_output_tokens

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str | None:
        return self._model

    def generate(self, prompt: str, timeout_seconds: float | None = None) -> str:
        """Call the OpenAI Chat Completions endpoint.

        Raises:
            LLMTimeoutError, LLMAuthenticationError, LLMRateLimitError,
            LLMNetworkError, LLMResponseError
        """
        endpoint = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a log analysis assistant. Output ONLY valid JSON adhering to the specified schema.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._max_output_tokens,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        timeout = timeout_seconds if timeout_seconds is not None else 30.0

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"OpenAI API request timed out after {timeout} seconds.",
                timeout_seconds=timeout,
                provider="openai",
            ) from exc
        except requests.ConnectionError as exc:
            raise LLMNetworkError(
                "Failed to connect to OpenAI API endpoint.",
                provider="openai",
            ) from exc
        except requests.RequestException as exc:
            raise LLMNetworkError(
                f"Network transport error while contacting OpenAI: {exc!s}",
                provider="openai",
            ) from exc

        # Handle HTTP response status
        if response.status_code in (401, 403):
            raise LLMAuthenticationError(
                f"OpenAI authentication failed (HTTP {response.status_code}). Please verify LLM_API_KEY.",
                provider="openai",
            )
        if response.status_code == 429:
            raise LLMRateLimitError(
                "OpenAI rate limit or quota exceeded (HTTP 429).",
                provider="openai",
            )
        if response.status_code >= 500:
            raise LLMResponseError(
                f"OpenAI service returned an internal server error (HTTP {response.status_code}).",
                status_code=response.status_code,
                provider="openai",
            )
        if not response.ok:
            raise LLMResponseError(
                f"OpenAI returned unexpected status HTTP {response.status_code}.",
                status_code=response.status_code,
                provider="openai",
            )

        try:
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMResponseError(
                    "OpenAI response contained no generation choices.",
                    provider="openai",
                )
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise LLMResponseError(
                    "OpenAI returned empty message content.",
                    provider="openai",
                )
            return content.strip()
        except ValueError as exc:
            raise LLMResponseError(
                "OpenAI response was not valid JSON.",
                provider="openai",
            ) from exc


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Instantiate and return the configured LLMProvider.

    Args:
        settings: Optional Settings instance (defaults to singleton get_settings()).

    Returns:
        LLMProvider: Initialized provider instance.

    Raises:
        LLMConfigurationError: If the configured provider name is unknown or missing.
        LLMAuthenticationError: If required credentials for the provider are missing.
    """
    cfg = settings or get_settings()
    provider_name = (cfg.LLM_PROVIDER or "").strip().lower()

    if not provider_name:
        raise LLMConfigurationError(
            "LLM provider is not configured. Set LLM_PROVIDER in environment or .env."
        )

    if provider_name == "mock":
        return MockLLMProvider(
            model_name=cfg.LLM_MODEL or "mock-default",
        )

    if provider_name in ("openai", "azure_openai"):
        return OpenAIProvider(
            api_key=cfg.LLM_API_KEY,
            model=cfg.LLM_MODEL or "gpt-4o-mini",
            max_output_tokens=cfg.LLM_MAX_OUTPUT_TOKENS,
        )

    raise LLMConfigurationError(
        f"Unsupported LLM provider: '{cfg.LLM_PROVIDER}'. Supported providers: 'mock', 'openai'."
    )
