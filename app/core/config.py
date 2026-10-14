"""Application configuration management.

Provides typed, validated configuration settings using Pydantic Settings.
Environment variables override default settings. Credentials and sensitive
parameters are optional and never hardcoded.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LogLens AI application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General Application Settings
    APP_NAME: str = Field(default="LogLens AI", description="Application name")
    APP_ENV: str = Field(
        default="development",
        description="Deployment environment (e.g., development, test, production)",
    )
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    # Log Ingestion & Processing Limits
    MAX_LOG_SIZE_BYTES: int = Field(
        default=1_048_576,  # 1 MiB
        description="Maximum accepted raw log payload in bytes",
    )
    MAX_LOG_LINES: int = Field(
        default=20_000,
        description="Maximum accepted line count for log input",
    )
    MAX_LOG_LINE_LENGTH: int = Field(
        default=16_384,
        description="Maximum accepted character length for an individual line",
    )
    ALLOW_PARTIAL_ANALYSIS: bool = Field(
        default=False,
        description="Whether partial analysis is allowed on oversized logs",
    )

    # LLM Service Configuration (Optional; disabled by default)
    LLM_ENABLED: bool = Field(
        default=False,
        description="Whether LLM-assisted analysis is enabled",
    )
    LLM_PROVIDER: str | None = Field(
        default=None,
        description="Target LLM provider name (e.g., mock, openai, anthropic)",
    )
    LLM_API_KEY: str | None = Field(
        default=None,
        description="API key for the selected LLM provider",
    )
    LLM_MODEL: str | None = Field(
        default=None,
        description="Model name/identifier for LLM analysis",
    )
    LLM_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Timeout for LLM API calls in seconds",
    )

    @field_validator("MAX_LOG_SIZE_BYTES")
    @classmethod
    def validate_max_log_size(cls, value: int) -> int:
        """Ensure maximum log size in bytes is strictly positive."""
        if value <= 0:
            raise ValueError("MAX_LOG_SIZE_BYTES must be greater than 0")
        return value

    @field_validator("MAX_LOG_LINES")
    @classmethod
    def validate_max_log_lines(cls, value: int) -> int:
        """Ensure maximum log lines limit is strictly positive."""
        if value <= 0:
            raise ValueError("MAX_LOG_LINES must be greater than 0")
        return value

    @field_validator("MAX_LOG_LINE_LENGTH")
    @classmethod
    def validate_max_log_line_length(cls, value: int) -> int:
        """Ensure maximum log line length is strictly positive."""
        if value <= 0:
            raise ValueError("MAX_LOG_LINE_LENGTH must be greater than 0")
        return value

    @field_validator("LLM_TIMEOUT_SECONDS")
    @classmethod
    def validate_llm_timeout(cls, value: float) -> float:
        """Ensure LLM timeout in seconds is strictly positive."""
        if value <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS must be greater than 0")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings.

    Settings are loaded once from environment variables and optional .env file.
    Use get_settings.cache_clear() in tests to reset state when needed.
    """
    return Settings()
