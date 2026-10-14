"""Response schemas for LogLens AI REST API endpoints."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.analysis_metrics import AnalysisMetrics
from app.models.failure_event import FailureEvent
from app.models.failure_group import FailureGroup
from app.models.log_entry import ParsedLogEntry
from app.services.llm.schemas import AIAnalysis


class HealthResponse(BaseModel):
    """Liveness probe response indicating the process is running."""

    status: str = Field(default="ok", description="Liveness status of the service")
    service: str = Field(default="LogLens AI", description="Application service name")


class ReadyResponse(BaseModel):
    """Readiness probe response indicating operational and LLM capability state."""

    status: str = Field(
        default="ready", description="Readiness status for log analysis"
    )
    llm_enabled: bool = Field(
        ..., description="Whether LLM assistance is enabled in server configuration"
    )
    llm_available: bool = Field(
        ..., description="Whether configured LLM credentials and provider are usable"
    )


class ErrorDetail(BaseModel):
    """Standardized, machine-readable error payload."""

    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Sanitized, human-readable error description")
    request_id: str | None = Field(
        default=None, description="Unique correlation ID of the failed request"
    )
    line_number: int | None = Field(
        default=None, description="Source line number associated with the error"
    )
    limit: int | None = Field(
        default=None, description="Configured limit threshold if applicable"
    )
    actual: int | None = Field(
        default=None, description="Actual measured value that violated the limit"
    )


class ErrorResponse(BaseModel):
    """Envelope wrapping standard error details."""

    error: ErrorDetail


class AnalysisStatus(StrEnum):
    """Overall execution status of a log analysis request."""

    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    COMPLETED_WITH_FALLBACK = "completed_with_fallback"


class AnalyzeLogResponse(BaseModel):
    """Structured response container returned by POST /api/v1/analyze."""

    request_id: str = Field(
        ..., description="Unique correlation ID assigned to this analysis request"
    )
    status: AnalysisStatus = Field(..., description="Overall analysis lifecycle status")
    metrics: AnalysisMetrics = Field(
        ..., description="Deterministic aggregate metrics across the log payload"
    )
    parsed_entries: list[ParsedLogEntry] = Field(
        default_factory=list,
        description="Structured representation of each physical source line",
    )
    failure_events: list[FailureEvent] = Field(
        default_factory=list,
        description="Logical error events, exceptions, or test failures detected",
    )
    failure_groups: list[FailureGroup] = Field(
        default_factory=list,
        description="Recurring failure groups clustered by deterministic fingerprint",
    )
    parser_warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or limitations encountered during parsing",
    )
    ai_analysis: AIAnalysis | None = Field(
        default=None,
        description="Optional AI-assisted triage summary with verified citations",
    )
    analysis_source: Literal["llm", "fallback", "none"] = Field(
        default="none",
        description="Provenance of the ai_analysis section ('llm', 'fallback', or 'none')",
    )
    processing_time_ms: float = Field(
        ..., ge=0.0, description="Total server-side processing duration in milliseconds"
    )
