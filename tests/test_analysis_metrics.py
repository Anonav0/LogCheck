"""Tests for deterministic aggregate failure and recurrence metrics."""

from app.models.analysis_metrics import AnalysisMetrics
from app.models.failure_event import FailureEvent, FailureEventType
from app.models.log_entry import LogLevel
from app.services.grouping import (
    analyze_failures,
    compute_analysis_metrics,
    group_failures,
)
from app.services.log_parser import parse_log_text


def _event(
    event_id: str,
    exc: str,
    msg: str,
    line: int,
) -> FailureEvent:
    return FailureEvent(
        event_id=event_id,
        event_type=FailureEventType.EXCEPTION,
        exception_type=exc,
        message=msg,
        primary_line_number=line,
        start_line_number=line,
        end_line_number=line,
        line_numbers=[line],
        stack_trace=[],
        level=LogLevel.ERROR,
    )


class TestAnalysisMetrics:
    """Verify calculation of failure metrics and recurrence quantities."""

    def test_empty_metrics(self) -> None:
        """Verify metrics for empty input return zeroes."""
        metrics = compute_analysis_metrics(
            total_log_lines=0,
            total_error_entries=0,
            total_warning_entries=0,
            groups=[],
        )
        assert metrics.total_log_lines == 0
        assert metrics.total_error_entries == 0
        assert metrics.total_warning_entries == 0
        assert metrics.total_failure_events == 0
        assert metrics.unique_failure_groups == 0
        assert metrics.repeated_failure_groups == 0
        assert metrics.repeated_failure_events == 0
        assert metrics.most_frequent_failure_count == 0

    def test_mixed_singleton_and_repeated_groups_metrics(self) -> None:
        """Verify metrics matching the canonical specification: 4 + 2 + 1 = 7 events across 3 groups."""
        # Group A: 4 occurrences
        events_a = [
            _event(f"ev-a{i}", "ErrorA", "Message A", i * 10) for i in range(1, 5)
        ]
        # Group B: 2 occurrences
        events_b = [
            _event(f"ev-b{i}", "ErrorB", "Message B", i * 10) for i in range(1, 3)
        ]
        # Group C: 1 occurrence
        events_c = [_event("ev-c1", "ErrorC", "Message C", 100)]

        all_events = events_a + events_b + events_c
        groups = group_failures(all_events)

        metrics = compute_analysis_metrics(
            total_log_lines=200,
            total_error_entries=7,
            total_warning_entries=3,
            groups=groups,
        )

        assert metrics.total_log_lines == 200
        assert metrics.total_error_entries == 7
        assert metrics.total_warning_entries == 3
        assert metrics.total_failure_events == 7
        assert metrics.unique_failure_groups == 3
        assert metrics.repeated_failure_groups == 2
        assert metrics.repeated_failure_events == 6
        assert metrics.most_frequent_failure_count == 4

    def test_analyze_failures_integration(
        self, recurring_failures_log_text: str
    ) -> None:
        """Verify end-to-end analyze_failures integration on recurring_failures.log."""
        parsing_result = parse_log_text(recurring_failures_log_text)
        analysis = analyze_failures(parsing_result)

        assert isinstance(analysis.metrics, AnalysisMetrics)
        assert analysis.metrics.total_log_lines == parsing_result.total_lines
        assert analysis.metrics.total_error_entries == 4
        assert analysis.metrics.total_failure_events == 4
        assert analysis.metrics.unique_failure_groups == 2
        assert analysis.metrics.repeated_failure_groups == 1
        assert analysis.metrics.repeated_failure_events == 3
        assert analysis.metrics.most_frequent_failure_count == 3
        assert len(analysis.failure_groups) == 2
