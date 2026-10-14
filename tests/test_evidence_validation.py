"""Tests for evidence reference and integrity validation."""

from app.models.analysis_metrics import AnalysisMetrics, FailureAnalysisResult
from app.models.failure_event import FailureEvent, FailureEventType
from app.models.failure_group import FailureGroup
from app.models.log_entry import ParsedLogEntry
from app.models.parsing_result import ParsingResult
from app.services.evidence_validator import (
    validate_analysis_result,
    validate_parsing_result,
)
from app.services.grouping import analyze_failures
from app.services.log_parser import parse_log_text


class TestEvidenceValidationHappyPath:
    """Verify that legitimate parsing and analysis results pass evidence validation."""

    def test_sample_application_log_passes_integrity(
        self, sample_application_log_text: str
    ) -> None:
        """Verify sample_application.log parsing result passes evidence integrity checks."""
        parsing_result = parse_log_text(sample_application_log_text)
        val_result = validate_parsing_result(
            sample_application_log_text, parsing_result
        )
        assert val_result.is_valid is True
        assert len(val_result.errors) == 0
        assert val_result.validated_lines_count == parsing_result.total_lines

    def test_recurring_failures_analysis_passes_integrity(
        self, recurring_failures_log_text: str
    ) -> None:
        """Verify recurring_failures.log analysis result passes all group and metrics checks."""
        parsing_result = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing_result)
        val_result = validate_analysis_result(recurring_failures_log_text, analysis)
        assert val_result.is_valid is True
        assert len(val_result.errors) == 0
        assert val_result.validated_groups_count == len(analysis.failure_groups)


class TestEvidenceValidationCorruptedEntries:
    """Verify detection of corrupted line numbers and mismatched contents."""

    def test_out_of_range_line_number_detected(self) -> None:
        """Verify entry pointing to line beyond total_lines is flagged."""
        log = "line 1\nline 2"
        parsing_result = parse_log_text(log)
        # Corrupt entry 2 to point to line 999
        corrupted_entries = list(parsing_result.entries)
        corrupted_entries[1] = ParsedLogEntry(
            line_number=999,
            raw_line="line 2",
            message="line 2",
        )
        corrupted_result = ParsingResult(
            total_lines=2,
            entries=corrupted_entries,
            failure_events=parsing_result.failure_events,
        )

        val = validate_parsing_result(log, corrupted_result)
        assert val.is_valid is False
        assert any(e.code == "LINE_OUT_OF_RANGE" for e in val.errors)

    def test_raw_content_mismatch_detected(self) -> None:
        """Verify entry whose raw text does not match the source line is flagged."""
        log = "line 1\nline 2"
        parsing_result = parse_log_text(log)
        corrupted_entries = list(parsing_result.entries)
        corrupted_entries[0] = ParsedLogEntry(
            line_number=1,
            raw_line="fabricated content",
            message="fabricated content",
        )
        corrupted_result = ParsingResult(
            total_lines=2,
            entries=corrupted_entries,
            failure_events=parsing_result.failure_events,
        )

        val = validate_parsing_result(log, corrupted_result)
        assert val.is_valid is False
        assert any(e.code == "CONTENT_MISMATCH" for e in val.errors)


class TestEvidenceValidationCorruptedEvents:
    """Verify detection of invalid failure events, reversed ranges, and link mismatches."""

    def test_reversed_line_range_detected(self) -> None:
        """Verify event with start_line > end_line is flagged."""
        log = "2026-10-14 10:00:00 [ERROR] app: Error\nTraceback...\nValueError: boom"
        parsing_result = parse_log_text(log)
        event = parsing_result.failure_events[0]
        corrupted_event = FailureEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            exception_type=event.exception_type,
            message=event.message,
            primary_line_number=event.primary_line_number,
            start_line_number=3,  # Reversed: start 3 > end 1
            end_line_number=1,
            line_numbers=[1, 2, 3],
            stack_trace=event.stack_trace,
        )
        corrupted_result = ParsingResult(
            total_lines=parsing_result.total_lines,
            entries=parsing_result.entries,
            failure_events=[corrupted_event],
        )

        val = validate_parsing_result(log, corrupted_result)
        assert val.is_valid is False
        assert any(e.code == "REVERSED_LINE_RANGE" for e in val.errors)

    def test_duplicate_event_id_detected(self) -> None:
        """Verify two failure events sharing the same event_id are flagged."""
        log = "2026-10-14 10:00:00 [ERROR] app: Err1\n2026-10-14 10:00:01 [ERROR] app: Err2"
        parsing_result = parse_log_text(log)
        # Duplicate the first event
        dup_event = parsing_result.failure_events[0]
        corrupted_result = ParsingResult(
            total_lines=parsing_result.total_lines,
            entries=parsing_result.entries,
            failure_events=[dup_event, dup_event],
        )

        val = validate_parsing_result(log, corrupted_result)
        assert val.is_valid is False
        assert any(e.code == "DUPLICATE_EVENT_ID" for e in val.errors)

    def test_inconsistent_event_link_detected(self) -> None:
        """Verify event claiming a line whose entry has a different failure_event_id is flagged."""
        log = "2026-10-14 10:00:00 [ERROR] app: Error"
        parsing_result = parse_log_text(log)
        # Entry has failure_event_id="event-1", change event to "event-99"
        ev = parsing_result.failure_events[0]
        corrupted_ev = FailureEvent(
            event_id="event-99",
            event_type=ev.event_type,
            message=ev.message,
            primary_line_number=1,
            start_line_number=1,
            end_line_number=1,
            line_numbers=[1],
        )
        corrupted_result = ParsingResult(
            total_lines=1,
            entries=parsing_result.entries,
            failure_events=[corrupted_ev],
        )

        val = validate_parsing_result(log, corrupted_result)
        assert val.is_valid is False
        assert any(e.code == "INCONSISTENT_EVENT_LINK" for e in val.errors)


class TestEvidenceValidationCorruptedGroupsAndMetrics:
    """Verify validation on FailureGroup properties and aggregate metrics consistency."""

    def test_invalid_fingerprint_format_detected(self) -> None:
        """Verify a non-SHA-256 fingerprint string is flagged."""
        log = "2026-10-14 10:00:00 [ERROR] app: Error"
        analysis = analyze_failures(parse_log_text(log))

        # Corrupt group fingerprint to non-hex string
        corrupted_group = FailureGroup(
            fingerprint="not-a-valid-sha256-hash",
            title="Corrupted Group",
            failure_category=FailureEventType.EXPLICIT_ERROR,
            representative_message="Error",
            occurrence_count=1,
            occurrences=analysis.failure_groups[0].occurrences,
            line_numbers=[1],
            first_seen_line=1,
            last_seen_line=1,
        )
        corrupted_analysis = FailureAnalysisResult(
            parsing_result=analysis.parsing_result,
            failure_groups=[corrupted_group],
            metrics=analysis.metrics,
        )

        val = validate_analysis_result(log, corrupted_analysis)
        assert val.is_valid is False
        assert any(e.code == "INVALID_FINGERPRINT_FORMAT" for e in val.errors)

    def test_group_occurrence_count_mismatch_detected(self) -> None:
        """Verify group occurrence_count differing from len(occurrences) is flagged."""
        log = "2026-10-14 10:00:00 [ERROR] app: Error"
        analysis = analyze_failures(parse_log_text(log))

        g = analysis.failure_groups[0]
        corrupted_group = FailureGroup(
            fingerprint=g.fingerprint,
            title=g.title,
            failure_category=g.failure_category,
            representative_message=g.representative_message,
            occurrence_count=99,  # Mismatch: occurrences has 1 item
            occurrences=g.occurrences,
            line_numbers=g.line_numbers,
            first_seen_line=g.first_seen_line,
            last_seen_line=g.last_seen_line,
        )
        corrupted_analysis = FailureAnalysisResult(
            parsing_result=analysis.parsing_result,
            failure_groups=[corrupted_group],
            metrics=analysis.metrics,
        )

        val = validate_analysis_result(log, corrupted_analysis)
        assert val.is_valid is False
        assert any(e.code == "OCCURRENCE_COUNT_MISMATCH" for e in val.errors)

    def test_metrics_inconsistency_detected(self) -> None:
        """Verify metrics differing from underlying data are flagged."""
        log = "2026-10-14 10:00:00 [ERROR] app: Error"
        analysis = analyze_failures(parse_log_text(log))

        corrupted_metrics = AnalysisMetrics(
            total_log_lines=1,
            total_error_entries=1,
            total_warning_entries=0,
            total_failure_events=999,  # Mismatch: only 1 event
            unique_failure_groups=1,
            repeated_failure_groups=0,
            repeated_failure_events=0,
            most_frequent_failure_count=1,
        )
        corrupted_analysis = FailureAnalysisResult(
            parsing_result=analysis.parsing_result,
            failure_groups=analysis.failure_groups,
            metrics=corrupted_metrics,
        )

        val = validate_analysis_result(log, corrupted_analysis)
        assert val.is_valid is False
        assert any(e.code == "METRIC_TOTAL_EVENTS_MISMATCH" for e in val.errors)
