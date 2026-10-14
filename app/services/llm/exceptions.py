"""LLM integration exceptions.

Defines provider-independent exception classes representing failures across
configuration, authentication, network transport, timeouts, response validation,
and evidence verification.
"""

from app.core.exceptions import LogLensError


class LLMError(LogLensError):
    """Base class for all LLM integration errors."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider

    def __str__(self) -> str:
        if self.provider:
            return f"[{self.provider}] {self.message}"
        return self.message


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is invalid, missing, or unsupported."""


class LLMAuthenticationError(LLMError):
    """Raised when provider authentication fails (e.g., invalid or expired API key)."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM request exceeds the configured timeout budget."""

    def __init__(
        self,
        message: str,
        timeout_seconds: float | None = None,
        provider: str | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.timeout_seconds = timeout_seconds


class LLMRateLimitError(LLMError):
    """Raised when provider rate limits or quotas are exceeded."""


class LLMNetworkError(LLMError):
    """Raised when network connectivity to the provider fails."""


class LLMResponseError(LLMError):
    """Raised when the provider returns an unexpected HTTP or protocol status."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        provider: str | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.status_code = status_code


class LLMResponseValidationError(LLMError):
    """Raised when the provider output fails JSON decoding or schema validation."""


class LLMEvidenceVerificationError(LLMError):
    """Raised when AI-generated evidence references fail verification against source logs."""

