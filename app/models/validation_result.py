"""Data models for input validation and evidence integrity results."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ValidationSeverity(StrEnum):
    """Severity classification of a validation finding."""

    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    """Represents a discrete validation issue or diagnostic finding."""

    code: str = Field(..., description="Stable, programmatic error code.")
    message: str = Field(..., description="Human-readable explanation of the issue.")
    severity: ValidationSeverity = Field(
        default=ValidationSeverity.ERROR,
        description="Whether this issue is a blocking error or a nonblocking warning.",
    )
    line_number: int | None = Field(
        default=None, description="1-based source line number if associated."
    )
    entity_id: str | None = Field(
        default=None, description="Event or group identifier if associated."
    )
    limit: int | None = Field(
        default=None, description="Configured limit threshold if relevant."
    )
    actual: int | None = Field(
        default=None, description="Observed value that exceeded limit if relevant."
    )


class ValidatedLogInput(BaseModel):
    """Container for successfully validated raw log text and its structural metrics."""

    raw_text: str = Field(..., description="The verified raw log text payload.")
    byte_size: int = Field(..., ge=0, description="Measured UTF-8 byte length.")
    line_count: int = Field(..., ge=1, description="Number of canonical source lines.")
    is_valid: bool = Field(
        default=True, description="Indicates that all validation checks succeeded."
    )


class EvidenceValidationResult(BaseModel):
    """Structured report verifying evidence references against the original source log."""

    is_valid: bool = Field(
        ..., description="True if no blocking integrity errors were detected."
    )
    errors: list[ValidationIssue] = Field(
        default_factory=list, description="Blocking integrity errors detected."
    )
    warnings: list[ValidationIssue] = Field(
        default_factory=list, description="Nonblocking notices or suspicious evidence."
    )
    validated_lines_count: int = Field(
        default=0, ge=0, description="Total source lines cross-referenced."
    )
    validated_events_count: int = Field(
        default=0, ge=0, description="Total failure events verified."
    )
    validated_groups_count: int = Field(
        default=0, ge=0, description="Total failure groups verified."
    )
