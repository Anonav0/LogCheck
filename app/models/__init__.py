"""Domain and data models for LogLens AI."""

from app.models.analysis_metrics import AnalysisMetrics, FailureAnalysisResult
from app.models.failure_event import FailureEvent, FailureEventType
from app.models.failure_group import FailureGroup, FailureOccurrence
from app.models.log_entry import (
    LineCategory,
    LogLevel,
    ParsedLogEntry,
    normalize_log_level,
)
from app.models.parsing_result import ParsingResult
from app.models.validation_result import (
    EvidenceValidationResult,
    ValidatedLogInput,
    ValidationIssue,
    ValidationSeverity,
)

__all__ = [
    "AnalysisMetrics",
    "EvidenceValidationResult",
    "FailureAnalysisResult",
    "FailureEvent",
    "FailureEventType",
    "FailureGroup",
    "FailureOccurrence",
    "LineCategory",
    "LogLevel",
    "ParsedLogEntry",
    "ParsingResult",
    "ValidatedLogInput",
    "ValidationIssue",
    "ValidationSeverity",
    "normalize_log_level",
]
