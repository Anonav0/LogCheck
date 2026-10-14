"""Evidence reference and integrity validation service.

Verifies that all parsed log entries, failure events, stack trace lines,
failure groups, and aggregate metrics reference valid, unshifted source lines
in the original log payload.
"""

import re

from app.core.config import Settings
from app.core.exceptions import EvidenceIntegrityError
from app.models.analysis_metrics import FailureAnalysisResult
from app.models.log_entry import LogLevel
from app.models.parsing_result import ParsingResult
from app.models.validation_result import (
    EvidenceValidationResult,
    ValidationIssue,
    ValidationSeverity,
)
from app.services.grouping import analyze_failures
from app.services.input_validator import validate_log_input
from app.services.log_parser import parse_log_text
from app.utils.line_references import split_source_lines

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def validate_parsing_result(
    original_log: str, result: ParsingResult
) -> EvidenceValidationResult:
    """Validate that all entries and failure events in a ParsingResult accurately match original_log.

    Checks:
        - Total lines and line order consistency with canonical split.
        - Entry line numbering is 1-based, monotonic, and in range.
        - Entry raw line content matches original source line.
        - Failure event line references (start, primary, end, line_numbers) are in range.
        - Event ranges are not inverted (start <= end).
        - Every failure_event_id is uniquely claimed and cross-linked to entries.
        - Aggregate parsing metrics are mathematically consistent with entry collections.
    """
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    canonical_lines = split_source_lines(original_log)
    total_lines = len(canonical_lines)

    # 1. Total lines check
    if result.total_lines != total_lines:
        errors.append(
            ValidationIssue(
                code="TOTAL_LINES_MISMATCH",
                message=(
                    f"ParsingResult total_lines ({result.total_lines}) does not match "
                    f"canonical source line count ({total_lines})."
                ),
                limit=total_lines,
                actual=result.total_lines,
            )
        )

    # 2. Entries check
    if len(result.entries) != total_lines:
        errors.append(
            ValidationIssue(
                code="ENTRY_COUNT_MISMATCH",
                message=(
                    f"Parsed entries count ({len(result.entries)}) does not match "
                    f"source line count ({total_lines})."
                ),
                limit=total_lines,
                actual=len(result.entries),
            )
        )

    for idx, entry in enumerate(result.entries, start=1):
        # 1-based order check
        if entry.line_number != idx:
            errors.append(
                ValidationIssue(
                    code="NON_MONOTONIC_LINE_NUMBER",
                    message=f"Entry at index {idx} has mismatched line number {entry.line_number}.",
                    line_number=entry.line_number,
                )
            )

        if not (1 <= entry.line_number <= total_lines):
            errors.append(
                ValidationIssue(
                    code="LINE_OUT_OF_RANGE",
                    message=f"Entry line number {entry.line_number} is out of source range [1, {total_lines}].",
                    line_number=entry.line_number,
                )
            )

        # Content match check
        if idx <= total_lines:
            expected_raw = canonical_lines[idx - 1]
            if entry.raw_line != expected_raw:
                errors.append(
                    ValidationIssue(
                        code="CONTENT_MISMATCH",
                        message=f"Entry at line {idx} raw text does not match original source line.",
                        line_number=idx,
                    )
                )

    # 3. Failure events check
    seen_event_ids: set[str] = set()

    for event in result.failure_events:
        # Event ID uniqueness
        if event.event_id in seen_event_ids:
            errors.append(
                ValidationIssue(
                    code="DUPLICATE_EVENT_ID",
                    message=f"Duplicate failure event ID '{event.event_id}' detected.",
                    entity_id=event.event_id,
                )
            )
        seen_event_ids.add(event.event_id)

        # Range validity
        if event.start_line_number > event.end_line_number:
            errors.append(
                ValidationIssue(
                    code="REVERSED_LINE_RANGE",
                    message=(
                        f"Event '{event.event_id}' has reversed line range: "
                        f"start ({event.start_line_number}) > end ({event.end_line_number})."
                    ),
                    entity_id=event.event_id,
                )
            )

        # Line bounds checks
        for ln in (
            event.primary_line_number,
            event.start_line_number,
            event.end_line_number,
        ):
            if not (1 <= ln <= total_lines):
                errors.append(
                    ValidationIssue(
                        code="EVENT_LINE_OUT_OF_RANGE",
                        message=f"Event '{event.event_id}' references out-of-range line {ln}.",
                        entity_id=event.event_id,
                        line_number=ln,
                    )
                )

        # Line numbers array checks
        for ln in event.line_numbers:
            if not (1 <= ln <= total_lines):
                errors.append(
                    ValidationIssue(
                        code="EVENT_LINE_OUT_OF_RANGE",
                        message=f"Event '{event.event_id}' references out-of-range line {ln}.",
                        entity_id=event.event_id,
                        line_number=ln,
                    )
                )

        if event.line_numbers != sorted(set(event.line_numbers)):
            warnings.append(
                ValidationIssue(
                    code="UNSORTED_EVENT_LINES",
                    message=f"Event '{event.event_id}' line_numbers list is not sorted or contains duplicates.",
                    severity=ValidationSeverity.WARNING,
                    entity_id=event.event_id,
                )
            )

        if event.primary_line_number not in event.line_numbers:
            errors.append(
                ValidationIssue(
                    code="PRIMARY_LINE_NOT_IN_EVENT",
                    message=(
                        f"Event '{event.event_id}' primary line {event.primary_line_number} "
                        f"is not included in its line_numbers."
                    ),
                    entity_id=event.event_id,
                    line_number=event.primary_line_number,
                )
            )

        # Cross-linking check: verify each claimed entry has failure_event_id matching this event
        for ln in event.line_numbers:
            if 1 <= ln <= len(result.entries):
                linked_entry = result.entries[ln - 1]
                if linked_entry.failure_event_id != event.event_id:
                    errors.append(
                        ValidationIssue(
                            code="INCONSISTENT_EVENT_LINK",
                            message=(
                                f"Line {ln} claimed by event '{event.event_id}' has "
                                f"mismatched failure_event_id '{linked_entry.failure_event_id}'."
                            ),
                            entity_id=event.event_id,
                            line_number=ln,
                        )
                    )

    # 4. Metrics consistency on ParsingResult
    computed_errors = sum(
        1 for e in result.entries if e.level in (LogLevel.ERROR, LogLevel.CRITICAL)
    )
    if result.error_count != computed_errors:
        errors.append(
            ValidationIssue(
                code="METRIC_MISMATCH_ERROR_COUNT",
                message=(
                    f"Reported error_count ({result.error_count}) does not match "
                    f"computed error entries ({computed_errors})."
                ),
                limit=computed_errors,
                actual=result.error_count,
            )
        )

    computed_warnings = sum(1 for e in result.entries if e.level == LogLevel.WARNING)
    if result.warning_count != computed_warnings:
        errors.append(
            ValidationIssue(
                code="METRIC_MISMATCH_WARNING_COUNT",
                message=(
                    f"Reported warning_count ({result.warning_count}) does not match "
                    f"computed warning entries ({computed_warnings})."
                ),
                limit=computed_warnings,
                actual=result.warning_count,
            )
        )

    if result.failure_event_count != len(result.failure_events):
        errors.append(
            ValidationIssue(
                code="METRIC_MISMATCH_EVENT_COUNT",
                message=(
                    f"Reported failure_event_count ({result.failure_event_count}) does not match "
                    f"len(failure_events) ({len(result.failure_events)})."
                ),
                limit=len(result.failure_events),
                actual=result.failure_event_count,
            )
        )

    return EvidenceValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        validated_lines_count=total_lines,
        validated_events_count=len(result.failure_events),
        validated_groups_count=0,
    )


def validate_analysis_result(
    original_log: str, analysis: FailureAnalysisResult
) -> EvidenceValidationResult:
    """Validate all evidence in a FailureAnalysisResult (parsing, grouping, and metrics).

    Checks:
        - Passes all parsing result checks from validate_parsing_result().
        - Validates SHA-256 fingerprint format on every group.
        - Verifies group occurrence counts match occurrences collection.
        - Verifies group first_seen_line and last_seen_line agree with occurrences.
        - Verifies group line_numbers is exact sorted unique union of occurrence lines.
        - Verifies analysis metrics match groups and parsing counts mathematically.
    """
    # 1. Base validation on parsing result
    base_val = validate_parsing_result(original_log, analysis.parsing_result)
    errors = list(base_val.errors)
    warnings = list(base_val.warnings)

    total_lines = base_val.validated_lines_count
    groups = analysis.failure_groups

    # 2. Group checks
    for group in groups:
        # Check fingerprint format
        if not _SHA256_HEX_PATTERN.match(group.fingerprint):
            errors.append(
                ValidationIssue(
                    code="INVALID_FINGERPRINT_FORMAT",
                    message=(
                        f"Group '{group.title}' has invalid fingerprint format: "
                        f"'{group.fingerprint}' (expected 64-char hex SHA-256)."
                    ),
                    entity_id=group.fingerprint,
                )
            )

        # Check occurrence count consistency
        if group.occurrence_count != len(group.occurrences):
            errors.append(
                ValidationIssue(
                    code="OCCURRENCE_COUNT_MISMATCH",
                    message=(
                        f"Group '{group.fingerprint}' declared occurrence_count "
                        f"({group.occurrence_count}) != len(occurrences) ({len(group.occurrences)})."
                    ),
                    entity_id=group.fingerprint,
                    limit=len(group.occurrences),
                    actual=group.occurrence_count,
                )
            )

        if not group.occurrences:
            errors.append(
                ValidationIssue(
                    code="EMPTY_GROUP_OCCURRENCES",
                    message=f"Group '{group.fingerprint}' contains zero occurrences.",
                    entity_id=group.fingerprint,
                )
            )
            continue

        # Check first_seen and last_seen positions
        expected_first = min(occ.primary_line_number for occ in group.occurrences)
        expected_last = max(occ.primary_line_number for occ in group.occurrences)
        if group.first_seen_line != expected_first:
            errors.append(
                ValidationIssue(
                    code="FIRST_SEEN_LINE_MISMATCH",
                    message=(
                        f"Group '{group.fingerprint}' first_seen_line ({group.first_seen_line}) "
                        f"!= expected ({expected_first})."
                    ),
                    entity_id=group.fingerprint,
                    limit=expected_first,
                    actual=group.first_seen_line,
                )
            )

        if group.last_seen_line != expected_last:
            errors.append(
                ValidationIssue(
                    code="LAST_SEEN_LINE_MISMATCH",
                    message=(
                        f"Group '{group.fingerprint}' last_seen_line ({group.last_seen_line}) "
                        f"!= expected ({expected_last})."
                    ),
                    entity_id=group.fingerprint,
                    limit=expected_last,
                    actual=group.last_seen_line,
                )
            )

        # Check combined line numbers
        expected_lines = sorted(
            {ln for occ in group.occurrences for ln in occ.line_numbers}
        )
        if group.line_numbers != expected_lines:
            errors.append(
                ValidationIssue(
                    code="GROUP_LINES_MISMATCH",
                    message=f"Group '{group.fingerprint}' line_numbers do not match occurrences union.",
                    entity_id=group.fingerprint,
                )
            )

        for ln in group.line_numbers:
            if not (1 <= ln <= total_lines):
                errors.append(
                    ValidationIssue(
                        code="GROUP_LINE_OUT_OF_RANGE",
                        message=f"Group '{group.fingerprint}' contains out-of-range line {ln}.",
                        entity_id=group.fingerprint,
                        line_number=ln,
                    )
                )

    # 3. Metrics consistency checks
    m = analysis.metrics
    p = analysis.parsing_result

    if m.total_log_lines != p.total_lines:
        errors.append(
            ValidationIssue(
                code="METRIC_TOTAL_LINES_MISMATCH",
                message=f"Metrics total_log_lines ({m.total_log_lines}) != parsing total_lines ({p.total_lines}).",
                limit=p.total_lines,
                actual=m.total_log_lines,
            )
        )

    if m.total_error_entries != p.error_count:
        errors.append(
            ValidationIssue(
                code="METRIC_ERROR_COUNT_MISMATCH",
                message=f"Metrics total_error_entries ({m.total_error_entries}) != parsing error_count ({p.error_count}).",
                limit=p.error_count,
                actual=m.total_error_entries,
            )
        )

    if m.total_warning_entries != p.warning_count:
        errors.append(
            ValidationIssue(
                code="METRIC_WARNING_COUNT_MISMATCH",
                message=f"Metrics total_warning_entries ({m.total_warning_entries}) != parsing warning_count ({p.warning_count}).",
                limit=p.warning_count,
                actual=m.total_warning_entries,
            )
        )

    expected_total_events = sum(g.occurrence_count for g in groups)
    if m.total_failure_events != expected_total_events:
        errors.append(
            ValidationIssue(
                code="METRIC_TOTAL_EVENTS_MISMATCH",
                message=f"Metrics total_failure_events ({m.total_failure_events}) != group occurrences ({expected_total_events}).",
                limit=expected_total_events,
                actual=m.total_failure_events,
            )
        )

    if m.unique_failure_groups != len(groups):
        errors.append(
            ValidationIssue(
                code="METRIC_UNIQUE_GROUPS_MISMATCH",
                message=f"Metrics unique_failure_groups ({m.unique_failure_groups}) != len(groups) ({len(groups)}).",
                limit=len(groups),
                actual=m.unique_failure_groups,
            )
        )

    expected_repeated_groups = sum(1 for g in groups if g.occurrence_count > 1)
    if m.repeated_failure_groups != expected_repeated_groups:
        errors.append(
            ValidationIssue(
                code="METRIC_REPEATED_GROUPS_MISMATCH",
                message=f"Metrics repeated_failure_groups ({m.repeated_failure_groups}) != expected ({expected_repeated_groups}).",
                limit=expected_repeated_groups,
                actual=m.repeated_failure_groups,
            )
        )

    expected_repeated_events = sum(
        g.occurrence_count for g in groups if g.occurrence_count > 1
    )
    if m.repeated_failure_events != expected_repeated_events:
        errors.append(
            ValidationIssue(
                code="METRIC_REPEATED_EVENTS_MISMATCH",
                message=f"Metrics repeated_failure_events ({m.repeated_failure_events}) != expected ({expected_repeated_events}).",
                limit=expected_repeated_events,
                actual=m.repeated_failure_events,
            )
        )

    expected_most_frequent = max((g.occurrence_count for g in groups), default=0)
    if m.most_frequent_failure_count != expected_most_frequent:
        errors.append(
            ValidationIssue(
                code="METRIC_MOST_FREQUENT_MISMATCH",
                message=f"Metrics most_frequent_failure_count ({m.most_frequent_failure_count}) != expected ({expected_most_frequent}).",
                limit=expected_most_frequent,
                actual=m.most_frequent_failure_count,
            )
        )

    return EvidenceValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        validated_lines_count=total_lines,
        validated_events_count=len(p.failure_events),
        validated_groups_count=len(groups),
    )


def run_validated_analysis(
    log_text: str, settings: Settings | None = None
) -> FailureAnalysisResult:
    """Execute end-to-end analysis with full input and evidence integrity validation.

    Pipeline:
        1. Validate raw log input (size, encoding, line limits).
        2. Parse validated log into structured entries and failure events.
        3. Group recurring failures by fingerprint.
        4. Validate evidence references and metrics against original input.
        5. Return FailureAnalysisResult or raise EvidenceIntegrityError.

    Raises:
        InputValidationError: If input validation fails.
        EvidenceIntegrityError: If evidence validation fails.
    """
    validated_input = validate_log_input(log_text, settings=settings)
    parsing_result = parse_log_text(validated_input.raw_text)
    analysis_result = analyze_failures(parsing_result)

    evidence_val = validate_analysis_result(validated_input.raw_text, analysis_result)
    if not evidence_val.is_valid:
        first_err = evidence_val.errors[0]
        raise EvidenceIntegrityError(
            code=first_err.code,
            message=first_err.message,
            entity_id=first_err.entity_id,
            line_number=first_err.line_number,
        )

    return analysis_result
