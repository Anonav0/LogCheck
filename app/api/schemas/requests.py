"""Request schemas for LogLens AI REST API endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalyzeLogRequest(BaseModel):
    """Payload schema for POST /api/v1/analyze."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "log_text": "2026-10-14 10:30:00 [ERROR] app.service: Database connection failed after 5000ms",
                "include_ai": False,
            }
        },
    )

    log_text: str = Field(
        ...,
        min_length=1,
        description="Raw application or test log text to process and analyze",
    )
    include_ai: bool = Field(
        default=False,
        description="Whether to execute AI-assisted failure interpretation (falls back safely if unavailable)",
    )

    @field_validator("log_text")
    @classmethod
    def validate_non_whitespace(cls, value: str) -> str:
        """Reject empty or whitespace-only log text."""
        if not value or not value.strip():
            raise ValueError("log_text cannot be empty or contain only whitespace.")
        return value

