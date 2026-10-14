"""Data models for log parsing results and aggregate metrics."""

from pydantic import BaseModel, Field

from app.models.failure_event import FailureEvent
from app.models.log_entry import ParsedLogEntry


class ParsingResult(BaseModel):
    """Aggregate output from parsing a log payload."""

    total_lines: int = Field(
        default=0,
        ge=0,
        description="Total number of source lines processed.",
    )
    entries: list[ParsedLogEntry] = Field(
        default_factory=list,
        description="All parsed entries in original source order.",
    )
    failure_events: list[FailureEvent] = Field(
        default_factory=list,
        description="All distinct logical failure events detected.",
    )
    error_count: int = Field(
        default=0,
        ge=0,
        description="Count of parsed entries with ERROR or CRITICAL severity.",
    )
    warning_count: int = Field(
        default=0,
        ge=0,
        description="Count of parsed entries with WARNING severity.",
    )
    failure_event_count: int = Field(
        default=0,
        ge=0,
        description="Total number of distinct failure events identified.",
    )
    stack_trace_line_count: int = Field(
        default=0,
        ge=0,
        description="Total lines classified as stack frame or traceback evidence.",
    )
    parser_warnings: list[str] = Field(
        default_factory=list,
        description="Nonfatal parsing notices or limitations encountered during parsing.",
    )
