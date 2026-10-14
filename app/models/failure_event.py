from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.log_entry import LogLevel


class FailureEventType(StrEnum):
    """Classification type of a logical failure event."""

    EXCEPTION = "exception"
    ASSERTION_FAILURE = "assertion_failure"
    EXPLICIT_ERROR = "explicit_error"
    TEST_FAILURE = "test_failure"


class FailureEvent(BaseModel):
    """Represents a single logical failure event spanning one or more log lines."""

    event_id: str = Field(
        ...,
        description="Deterministic identifier unique within the current analysis result.",
    )
    event_type: FailureEventType = Field(
        ...,
        description="Categorization of the failure event.",
    )
    exception_type: str | None = Field(
        default=None,
        description="Exception class name or error type if recognizable.",
    )
    message: str = Field(
        ...,
        description="Primary failure or exception message.",
    )
    primary_line_number: int = Field(
        ...,
        ge=1,
        description="1-based line number of the primary error or exception declaration.",
    )
    start_line_number: int = Field(
        ...,
        ge=1,
        description="First 1-based source line belonging to this event's range.",
    )
    end_line_number: int = Field(
        ...,
        ge=1,
        description="Last 1-based source line belonging to this event's range.",
    )
    line_numbers: list[int] = Field(
        default_factory=list,
        description="Ordered list of all 1-based source lines associated with this event.",
    )
    stack_trace: list[str] = Field(
        default_factory=list,
        description="Ordered lines comprising the stack trace or failure traceback.",
    )
    timestamp: str | None = Field(
        default=None,
        description="Event timestamp if reliably associated with the primary entry.",
    )
    level: LogLevel | None = Field(
        default=None,
        description="Normalized severity if reliably available from the primary entry.",
    )
    logger_name: str | None = Field(
        default=None,
        description="Component or logger if reliably available from the primary entry.",
    )
