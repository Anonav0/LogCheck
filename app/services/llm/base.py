"""Base abstract interface for LLM providers."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract interface defining provider-independent LLM interaction."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique identifier of this provider (e.g., 'mock', 'openai')."""

    @property
    @abstractmethod
    def model_name(self) -> str | None:
        """Return the configured model name/identifier, or None if unspecified."""

    @abstractmethod
    def generate(self, prompt: str, timeout_seconds: float | None = None) -> str:
        """Execute a generation request with the given prompt and timeout.

        Args:
            prompt: The fully constructed, self-contained prompt string.
            timeout_seconds: Maximum time to wait for a response in seconds.

        Returns:
            Raw string response from the model (untrusted).

        Raises:
            LLMTimeoutError: If the request exceeds the timeout.
            LLMAuthenticationError: If credentials or permissions are rejected.
            LLMRateLimitError: If provider rate limits or quotas are hit.
            LLMNetworkError: If network connectivity or transport fails.
            LLMResponseError: If the provider returns an unexpected error status.
        """
