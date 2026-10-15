"""Fingerprinting and failure-grouping reliability tests for Phase 8.

Verifies:
- Stable SHA-256 fingerprints across 100 repeated executions
- Normalization of volatile UUIDs, request IDs, IP addresses, and timestamps
- Preservation of meaningful error codes and distinct exception types
- Deterministic group sorting (occurrence_count desc, first_seen_line asc)
- Deterministic occurrence sorting (line_number asc)
- First and last source line accuracy and occurrence counts
- Metric consistency with underlying failure events
"""

from app.models.failure_event import FailureEvent, FailureEventType
from app.services.fingerprinting import generate_fingerprint, normalize_failure_message
from app.services.grouping import analyze_failures
from app.services.log_parser import parse_log_text


class TestFingerprintStability:
    """Tests guaranteeing fingerprint determinism and invariant stability."""

    def test_repeated_hashing_identical_100_runs(self) -> None:
        event = FailureEvent(
            event_id="test-1",
            event_type=FailureEventType.EXCEPTION,
            exception_type="DatabaseConnectionError",
            message="Connection timeout to 10.0.0.1:5432 after 5000ms [req-7890]",
            primary_line_number=10,
            start_line_number=10,
            end_line_number=15,
            stack_trace=[
                'File "/app/db.py", line 42, in connect',
                "raise DatabaseConnectionError()",
            ],
        )
        fps = [generate_fingerprint(event) for _ in range(100)]
        assert len(set(fps)) == 1
        assert len(fps[0]) == 64  # Valid SHA-256 hex string

    def test_volatile_identifiers_normalized_out(self) -> None:
        msg1 = "Connection lost for request 123e4567-e89b-12d3-a456-426614174000"
        msg2 = "Connection lost for request 987fcdeb-51a2-43d7-9876-543210987654"

        norm1 = normalize_failure_message(msg1)
        norm2 = normalize_failure_message(msg2)
        assert norm1 == norm2
        assert "<UUID>" in norm1

        event1 = FailureEvent(
            event_id="e1",
            event_type=FailureEventType.EXCEPTION,
            exception_type="ConnectionError",
            message=msg1,
            primary_line_number=5,
            start_line_number=5,
            end_line_number=5,
        )
        event2 = FailureEvent(
            event_id="e2",
            event_type=FailureEventType.EXCEPTION,
            exception_type="ConnectionError",
            message=msg2,
            primary_line_number=99,
            start_line_number=99,
            end_line_number=102,
        )
        assert generate_fingerprint(event1) == generate_fingerprint(event2)

    def test_distinct_exception_types_produce_distinct_fingerprints(self) -> None:
        event_timeout = FailureEvent(
            event_id="e1",
            event_type=FailureEventType.EXCEPTION,
            exception_type="TimeoutError",
            message="Service unavailable: connection pool exhausted",
            primary_line_number=1,
            start_line_number=1,
            end_line_number=1,
        )
        event_conn = FailureEvent(
            event_id="e2",
            event_type=FailureEventType.EXCEPTION,
            exception_type="ConnectionError",
            message="Service unavailable: connection pool exhausted",
            primary_line_number=1,
            start_line_number=1,
            end_line_number=1,
        )
        event_none = FailureEvent(
            event_id="e3",
            event_type=FailureEventType.EXPLICIT_ERROR,
            exception_type=None,
            message="Service unavailable: connection pool exhausted",
            primary_line_number=1,
            start_line_number=1,
            end_line_number=1,
        )

        fp1 = generate_fingerprint(event_timeout)
        fp2 = generate_fingerprint(event_conn)
        fp3 = generate_fingerprint(event_none)

        assert len({fp1, fp2, fp3}) == 3

    def test_http_status_codes_preserved(self) -> None:
        msg_404 = "HTTP request failed with status 404 Not Found"
        msg_500 = "HTTP request failed with status 500 Internal Server Error"

        norm_404 = normalize_failure_message(msg_404)
        norm_500 = normalize_failure_message(msg_500)
        assert "404" in norm_404
        assert "500" in norm_500
        assert norm_404 != norm_500


class TestGroupingDeterminism:
    """Tests verifying deterministic failure group sorting, ranges, and metrics."""

    def test_group_ordering_by_frequency_then_line(self) -> None:
        """Groups must be ordered by occurrence_count DESC, then first_seen_line ASC."""
        raw_log = (
            "2026-10-15 10:00:01 ERROR worker.rare1 - RareError: Alpha occurred\n"  # 1 occurrence, line 1
            "2026-10-15 10:00:02 ERROR worker.common - CommonError: Beta occurred\n"  # 3 occurrences, line 2
            "2026-10-15 10:00:03 ERROR worker.common - CommonError: Beta occurred\n"
            "2026-10-15 10:00:04 ERROR worker.common - CommonError: Beta occurred\n"
            "2026-10-15 10:00:05 ERROR worker.mod - ModerateError: Gamma occurred\n"  # 2 occurrences, line 5
            "2026-10-15 10:00:06 ERROR worker.mod - ModerateError: Gamma occurred\n"
            "2026-10-15 10:00:07 ERROR worker.rare2 - AnotherRareError: Delta occurred\n"  # 1 occurrence, line 7
        )
        parsed = parse_log_text(raw_log)
        result = analyze_failures(parsed)

        groups = result.failure_groups
        assert len(groups) == 4

        # 1st group: CommonError (3 occurrences)
        assert groups[0].occurrence_count == 3
        assert (
            "CommonError" in groups[0].title
            or "Beta" in groups[0].representative_message
        )

        # 2nd group: ModerateError (2 occurrences)
        assert groups[1].occurrence_count == 2
        assert (
            "ModerateError" in groups[1].title
            or "Gamma" in groups[1].representative_message
        )

        # 3rd and 4th groups have 1 occurrence each -> tied counts ordered by first_seen_line ASC
        assert groups[2].occurrence_count == 1
        assert groups[3].occurrence_count == 1
        assert groups[2].first_seen_line < groups[3].first_seen_line
        assert groups[2].first_seen_line == 1
        assert groups[3].first_seen_line == 7

    def test_occurrence_ordering_within_group(self) -> None:
        """Occurrences within each group must be ordered strictly ascending by start_line_number."""
        raw_log = (
            "2026-10-15 10:00:01 ERROR worker - PoolTimeoutError: Timeout on worker\n"
            "2026-10-15 10:00:02 INFO worker - Heartbeat ok\n"
            "2026-10-15 10:00:03 ERROR worker - PoolTimeoutError: Timeout on worker\n"
            "2026-10-15 10:00:04 INFO worker - Heartbeat ok\n"
            "2026-10-15 10:00:05 ERROR worker - PoolTimeoutError: Timeout on worker\n"
        )
        parsed = parse_log_text(raw_log)
        result = analyze_failures(parsed)

        assert len(result.failure_groups) == 1
        group = result.failure_groups[0]
        assert group.occurrence_count == 3
        assert group.first_seen_line == 1
        assert group.last_seen_line == 5

        lines = [occ.start_line_number for occ in group.occurrences]
        assert lines == [1, 3, 5]
        assert lines == sorted(lines)

    def test_metrics_agree_with_underlying_data(self) -> None:
        raw_log = (
            "2026-10-15 10:00:01 ERROR worker - ErrorA: Issue A\n"
            "2026-10-15 10:00:02 ERROR worker - ErrorA: Issue A\n"
            "2026-10-15 10:00:03 ERROR worker - ErrorB: Issue B\n"
            "2026-10-15 10:00:04 ERROR worker - ErrorC: Issue C\n"
        )
        parsed = parse_log_text(raw_log)
        result = analyze_failures(parsed)

        assert result.metrics.total_failure_events == 4
        assert result.metrics.unique_failure_groups == 3  # ErrorA, ErrorB, ErrorC
        assert result.metrics.repeated_failure_groups == 1  # ErrorA repeated
        assert sum(g.occurrence_count for g in result.failure_groups) == 4
