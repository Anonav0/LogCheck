"""Tests for LLM provider abstraction, factory, and error translation."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core.config import Settings
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.services.llm.provider_factory import (
    MockLLMProvider,
    OpenAIProvider,
    get_llm_provider,
)


class TestMockLLMProvider:
    """Tests verifying behavior of MockLLMProvider for offline testing."""

    def test_default_mock_provider(self) -> None:
        provider = MockLLMProvider()
        assert provider.provider_name == "mock"
        assert provider.model_name == "mock-gpt-4o"
        assert provider.call_count == 0

        res = provider.generate("Analyze this log")
        assert provider.call_count == 1
        assert provider.last_prompt == "Analyze this log"
        assert "DatabaseConnectionError" in res

    def test_custom_response_and_generator(self) -> None:
        provider = MockLLMProvider(response_text='{"status": "ok"}')
        assert provider.generate("test") == '{"status": "ok"}'

        provider = MockLLMProvider(response_generator=lambda p: f"Echo: {p}")
        assert provider.generate("hello") == "Echo: hello"

    def test_simulated_exception(self) -> None:
        provider = MockLLMProvider(
            simulated_exception=LLMNetworkError(
                "Simulated network drop", provider="mock"
            )
        )
        with pytest.raises(LLMNetworkError) as exc_info:
            provider.generate("test")
        assert "Simulated network drop" in exc_info.value.message

    def test_simulated_timeout(self) -> None:
        provider = MockLLMProvider(simulated_delay=0.1)
        with pytest.raises(LLMTimeoutError) as exc_info:
            provider.generate("test", timeout_seconds=0.01)
        assert exc_info.value.timeout_seconds == 0.01


class TestOpenAIProvider:
    """Tests verifying OpenAI provider adapter and HTTP error translations."""

    def test_missing_api_key_raises_auth_error(self) -> None:
        with pytest.raises(LLMAuthenticationError) as exc_info:
            OpenAIProvider(api_key=None)
        assert "API key is missing" in exc_info.value.message
        assert exc_info.value.provider == "openai"

    @patch("app.services.llm.provider_factory.requests.post")
    def test_successful_openai_generation(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"summary": "Test passed"}'}}]
        }
        mock_post.return_value = mock_response

        provider = OpenAIProvider(api_key="sk-test-secret-12345", model="gpt-4o-mini")
        result = provider.generate("Test prompt", timeout_seconds=15.0)

        assert result == '{"summary": "Test passed"}'
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test-secret-12345"
        assert kwargs["timeout"] == 15.0

    @patch("app.services.llm.provider_factory.requests.post")
    def test_auth_error_translation_401(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        provider = OpenAIProvider(api_key="sk-invalid-key")
        with pytest.raises(LLMAuthenticationError) as exc_info:
            provider.generate("prompt")
        assert "401" in exc_info.value.message
        assert "sk-invalid-key" not in str(exc_info.value)  # Credential safety

    @patch("app.services.llm.provider_factory.requests.post")
    def test_rate_limit_error_translation_429(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        provider = OpenAIProvider(api_key="sk-test-key")
        with pytest.raises(LLMRateLimitError):
            provider.generate("prompt")

    @patch("app.services.llm.provider_factory.requests.post")
    def test_server_error_translation_500(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 503
        mock_post.return_value = mock_response

        provider = OpenAIProvider(api_key="sk-test-key")
        with pytest.raises(LLMResponseError) as exc_info:
            provider.generate("prompt")
        assert exc_info.value.status_code == 503

    @patch("app.services.llm.provider_factory.requests.post")
    def test_timeout_translation(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = requests.Timeout("Connection timed out")
        provider = OpenAIProvider(api_key="sk-test-key")
        with pytest.raises(LLMTimeoutError):
            provider.generate("prompt", timeout_seconds=5.0)

    @patch("app.services.llm.provider_factory.requests.post")
    def test_connection_error_translation(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = requests.ConnectionError("DNS failure")
        provider = OpenAIProvider(api_key="sk-test-key")
        with pytest.raises(LLMNetworkError):
            provider.generate("prompt")


class TestProviderFactory:
    """Tests verifying get_llm_provider factory resolution."""

    def test_mock_provider_selection(self) -> None:
        settings = Settings(LLM_PROVIDER="mock", LLM_MODEL="mock-v1", _env_file=None)
        provider = get_llm_provider(settings)
        assert isinstance(provider, MockLLMProvider)
        assert provider.provider_name == "mock"
        assert provider.model_name == "mock-v1"

    def test_openai_provider_selection(self) -> None:
        settings = Settings(
            LLM_PROVIDER="openai",
            LLM_API_KEY="sk-valid-key-12345",
            LLM_MODEL="gpt-4o",
            _env_file=None,
        )
        provider = get_llm_provider(settings)
        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == "openai"
        assert provider.model_name == "gpt-4o"

    def test_unknown_provider_raises_configuration_error(self) -> None:
        settings = Settings(LLM_PROVIDER="unknown_provider", _env_file=None)
        with pytest.raises(LLMConfigurationError) as exc_info:
            get_llm_provider(settings)
        assert "Unsupported LLM provider" in exc_info.value.message

    def test_empty_provider_raises_configuration_error(self) -> None:
        settings = Settings(LLM_PROVIDER=None, _env_file=None)
        with pytest.raises(LLMConfigurationError) as exc_info:
            get_llm_provider(settings)
        assert "not configured" in exc_info.value.message
