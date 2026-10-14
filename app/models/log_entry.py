from enum import StrEnum

from pydantic import BaseModel, Field


class LogLevel(StrEnum):
    """Normalized log severity levels."""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LineCategory(StrEnum):
    """Deterministic classification category for an individual log line."""

    NORMAL = "normal"
    WARNING = "warning"
    ERROR = "error"
    EXCEPTION = "exception"
    STACK_FRAME = "stack_frame"
    TRACEBACK_HEADER = "traceback_header"
    TEST_FAILURE = "test_failure"
    UNKNOWN = "unknown"


def normalize_log_level(raw_level: str | None) -> LogLevel | None:
    """Normalize common raw severity strings into canonical LogLevel enum members.

    Normalizations:
        WARN -> WARNING
        FATAL -> CRITICAL
    """
    if not raw_level:
        return None

    cleaned = raw_level.strip().upper()
    if cleaned in ("WARN", "WARNING"):
        return LogLevel.WARNING
    if cleaned in ("FATAL", "CRITICAL"):
        return LogLevel.CRITICAL
    if cleaned == "ERROR":
        return LogLevel.ERROR
    if cleaned == "INFO":
        return LogLevel.INFO
    if cleaned == "DEBUG":
        return LogLevel.DEBUG
    if cleaned == "TRACE":
        return LogLevel.TRACE

    return None


class ParsedLogEntry(BaseModel):
    """Represents an individual parsed source log line with metadata."""

    line_number: int = Field(
        ...,
        ge=1,
        description="Original 1-based line number in the submitted input.",
    )
    raw_line: str = Field(
        ...,
        description="Exact raw line content excluding line terminator.",
    )
    timestamp: str | None = Field(
        default=None,
        description="Recognized timestamp string when available, otherwise None.",
    )
    level: LogLevel | None = Field(
        default=None,
        description="Normalized log severity level if recognized.",
    )
    logger_name: str | None = Field(
        default=None,
        description="Component or logger name if recognized.",
    )
    message: str = Field(
        ...,
        description="Extracted message body, or raw line if message cannot be isolated.",
    )
    category: LineCategory = Field(
        default=LineCategory.NORMAL,
        description="Structural classification category for this line.",
    )
    failure_event_id: str | None = Field(
        default=None,
        description="Optional identifier linking this line to a discovered failure event.",
    )
