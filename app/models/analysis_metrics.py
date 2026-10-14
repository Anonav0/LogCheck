"""Data models for aggregate failure analysis metrics and results."""

from pydantic import BaseModel, Field

from app.models.failure_group import FailureGroup
from app.models.parsing_result import ParsingResult


class AnalysisMetrics(BaseModel):
    """Aggregate metrics quantifying log processing, failure volume, and recurrence."""

    total_log_lines: int = Field(
        default=0, ge=0, description="Total source lines processed."
    )
    total_error_entries: int = Field(
        default=0,
        ge=0,
        description="Entries explicitly classified as ERROR or CRITICAL.",
    )
    total_warning_entries: int = Field(
        default=0, ge=0, description="Entries explicitly classified as WARNING."
    )
    total_failure_events: int = Field(
        default=0, ge=0, description="Total individual failure events identified."
    )
    unique_failure_groups: int = Field(
        default=0, ge=0, description="Number of distinct failure fingerprints."
    )
    repeated_failure_groups: int = Field(
        default=0,
        ge=0,
        description="Number of failure groups with occurrence_count > 1.",
    )
    repeated_failure_events: int = Field(
        default=0,
        ge=0,
        description="Total occurrences belonging to repeated failure groups.",
    )
    most_frequent_failure_count: int = Field(
        default=0,
        ge=0,
        description="Largest occurrence count among groups, or 0 if no groups exist.",
    )


class FailureAnalysisResult(BaseModel):
    """Combined output containing Phase 2 parsing results, Phase 3 groups, and metrics."""

    parsing_result: ParsingResult = Field(
        ..., description="Underlying deterministic parsing result."
    )
    failure_groups: list[FailureGroup] = Field(
        default_factory=list, description="Ordered failure groups."
    )
    metrics: AnalysisMetrics = Field(
        ..., description="Deterministic failure and recurrence metrics."
    )
