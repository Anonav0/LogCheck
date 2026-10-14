"""Data models for failure groups and occurrences."""

from pydantic import BaseModel, Field

from app.models.failure_event import FailureEventType
from app.models.log_entry import LogLevel


class FailureOccurrence(BaseModel):
    """Represents a single occurrence instance of a failure within a group."""

    event_id: str = Field(..., description="Unique ID of the underlying FailureEvent.")
    primary_line_number: int = Field(
        ..., ge=1, description="Source line containing primary error/exception."
    )
    start_line_number: int = Field(
        ..., ge=1, description="First source line of occurrence range."
    )
    end_line_number: int = Field(
        ..., ge=1, description="Last source line of occurrence range."
    )
    line_numbers: list[int] = Field(
        default_factory=list,
        description="All 1-based source lines associated with this occurrence.",
    )
    original_message: str = Field(
        ..., description="Original raw failure message before normalization."
    )
    exception_type: str | None = Field(
        default=None, description="Exception class or error type if recognized."
    )
    timestamp: str | None = Field(
        default=None, description="Timestamp associated with this occurrence."
    )
    level: LogLevel | None = Field(
        default=None, description="Severity level of this occurrence."
    )
    logger_name: str | None = Field(
        default=None, description="Logger or component name of this occurrence."
    )


class FailureGroup(BaseModel):
    """Represents a collection of recurring failure events sharing a common fingerprint."""

    fingerprint: str = Field(
        ...,
        description="Deterministic SHA-256 fingerprint representing this failure signature.",
    )
    title: str = Field(
        ...,
        description="Short, human-readable descriptive title for the failure group.",
    )
    failure_category: FailureEventType = Field(
        ..., description="Failure category shared by this group."
    )
    exception_type: str | None = Field(
        default=None, description="Common exception type or None if not applicable."
    )
    representative_message: str = Field(
        ..., description="Normalized or representative failure message for this group."
    )
    occurrence_count: int = Field(
        default=1, ge=1, description="Total number of failure events in this group."
    )
    occurrences: list[FailureOccurrence] = Field(
        default_factory=list,
        description="Ordered list of individual occurrences in this group.",
    )
    line_numbers: list[int] = Field(
        default_factory=list,
        description="Sorted, unique list of all source line numbers across occurrences.",
    )
    first_seen_line: int = Field(
        ...,
        ge=1,
        description="Earliest primary source line number where this failure occurred.",
    )
    last_seen_line: int = Field(
        ...,
        ge=1,
        description="Latest primary source line number where this failure occurred.",
    )
    severity: LogLevel | None = Field(
        default=None, description="Aggregated severity level for this group."
    )
    component: str | None = Field(
        default=None,
        description="Common component or logger name, or None if mixed/unknown.",
    )
