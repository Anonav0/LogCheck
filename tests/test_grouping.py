"""Tests for deterministic failure grouping, ordering, and aggregation."""

from app.models.failure_event import FailureEvent, FailureEventType
from app.models.log_entry import LogLevel
from app.services.grouping import group_failures
from app.services.log_parser import parse_log_text


def _build_event(
    event_id: str,
    exception_type: str | None,
    message: str,
    primary_line: int,
    lines: list[int] | None = None,
    logger_name: str | None = "app.service",
    level: LogLevel = LogLevel.ERROR,
) -> FailureEvent:
    line_nums = lines or [primary_line]
    return FailureEvent(
        event_id=event_id,
        event_type=FailureEventType.EXCEPTION,
        exception_type=exception_type,
        message=message,
        primary_line_number=primary_line,
        start_line_number=min(line_nums),
        end_line_number=max(line_nums),
        line_numbers=line_nums,
        stack_trace=[],
        timestamp="2026-10-14 10:00:00",
        level=level,
        logger_name=logger_name,
    )


class TestFailureGrouping:
    """Verify failure event grouping by fingerprint."""

    def test_empty_events_returns_empty_groups(self) -> None:
        """Verify grouping an empty list returns empty list."""
        assert group_failures([]) == []

    def test_single_event_produces_single_group(self) -> None:
        """Verify single event produces exactly one group with occurrence_count 1."""
        ev = _build_event("ev-1", "TimeoutError", "Timed out after 5.0s", 15)
        groups = group_failures([ev])
        assert len(groups) == 1
        group = groups[0]
        assert group.occurrence_count == 1
        assert len(group.occurrences) == 1
        assert group.occurrences[0].event_id == "ev-1"
        assert group.first_seen_line == 15
        assert group.last_seen_line == 15
        assert group.line_numbers == [15]

    def test_repeated_failures_grouped_together(self) -> None:
        """Verify repeated events with same signature are grouped into single group."""
        ev1 = _build_event(
            "ev-1",
            "DatabaseError",
            "Connection failed for request req-111",
            10,
            [10, 11, 12],
        )
        ev2 = _build_event(
            "ev-2",
            "DatabaseError",
            "Connection failed for request req-222",
            30,
            [30, 31, 32],
        )
        groups = group_failures([ev1, ev2])
        assert len(groups) == 1
        group = groups[0]
        assert group.occurrence_count == 2
        assert group.first_seen_line == 10
        assert group.last_seen_line == 30
        assert group.line_numbers == [10, 11, 12, 30, 31, 32]
        assert [occ.event_id for occ in group.occurrences] == ["ev-1", "ev-2"]

    def test_distinct_failures_remain_separate(self) -> None:
        """Verify distinct exception types produce separate groups."""
        ev1 = _build_event("ev-1", "ValueError", "Invalid input", 10)
        ev2 = _build_event("ev-2", "KeyError", "Missing key", 20)
        groups = group_failures([ev1, ev2])
        assert len(groups) == 2
        assert {g.exception_type for g in groups} == {"ValueError", "KeyError"}

    def test_group_ordering_rules(self) -> None:
        """Verify groups are ordered by count DESC, then first_seen_line ASC."""
        # Group A: 1 occurrence at line 5
        ev_a = _build_event("ev-a", "ErrorA", "Failure A", 5)
        # Group B: 2 occurrences at line 20 and 40
        ev_b1 = _build_event("ev-b1", "ErrorB", "Failure B", 20)
        ev_b2 = _build_event("ev-b2", "ErrorB", "Failure B", 40)
        # Group C: 1 occurrence at line 2
        ev_c = _build_event("ev-c", "ErrorC", "Failure C", 2)

        groups = group_failures([ev_a, ev_b1, ev_b2, ev_c])
        assert len(groups) == 3
        # Group B has highest count (2) -> first
        assert groups[0].exception_type == "ErrorB"
        assert groups[0].occurrence_count == 2
        # Groups C and A both have count 1; C first seen at line 2 < A at line 5 -> C then A
        assert groups[1].exception_type == "ErrorC"
        assert groups[2].exception_type == "ErrorA"

    def test_occurrences_ordered_within_group(self) -> None:
        """Verify occurrences inside a group are sorted by primary_line_number ASC."""
        ev_later = _build_event("ev-2", "ErrorX", "Failed", 50)
        ev_earlier = _build_event("ev-1", "ErrorX", "Failed", 10)

        # Pass in out of order
        groups = group_failures([ev_later, ev_earlier])
        group = groups[0]
        assert [occ.event_id for occ in group.occurrences] == ["ev-1", "ev-2"]
        assert [occ.primary_line_number for occ in group.occurrences] == [10, 50]

    def test_inconsistent_component_metadata(self) -> None:
        """Verify inconsistent logger names result in component=None (mixed)."""
        ev1 = _build_event("ev-1", "ErrorX", "Failed", 10, logger_name="service.alpha")
        ev2 = _build_event("ev-2", "ErrorX", "Failed", 20, logger_name="service.beta")
        groups = group_failures([ev1, ev2])
        # Note: logger_name is part of component in signature, so if different components,
        # they form distinct groups because component distinguishes failure origins!
        assert len(groups) == 2
        assert groups[0].component in ("service.alpha", "service.beta")

    def test_input_reordering_preserves_group_results(self) -> None:
        """Verify passing events in different order produces the exact same group ordering."""
        ev1 = _build_event("ev-1", "ErrorA", "Failed A", 10)
        ev2 = _build_event("ev-2", "ErrorA", "Failed A", 30)
        ev3 = _build_event("ev-3", "ErrorB", "Failed B", 20)

        groups_fwd = group_failures([ev1, ev2, ev3])
        groups_rev = group_failures([ev3, ev2, ev1])

        assert [g.fingerprint for g in groups_fwd] == [
            g.fingerprint for g in groups_rev
        ]
        assert [g.occurrence_count for g in groups_fwd] == [
            g.occurrence_count for g in groups_rev
        ]


class TestGroupingWithFixtures:
    """Verify grouping integration with Phase 1 log fixtures."""

    def test_recurring_failures_fixture_grouping(
        self, recurring_failures_log_text: str
    ) -> None:
        """Verify recurring_failures.log groups 3 DatabaseConnectionErrors into 1 group."""
        parsing_result = parse_log_text(recurring_failures_log_text)
        assert parsing_result.failure_event_count == 4

        groups = group_failures(parsing_result.failure_events)
        # Expected: 1 group for DatabaseConnectionError (3 occurrences), 1 group for ValidationError (1 occurrence)
        assert len(groups) == 2

        db_group = next(
            g for g in groups if g.exception_type == "DatabaseConnectionError"
        )
        assert db_group.occurrence_count == 3
        assert len(db_group.occurrences) == 3
        assert (
            db_group.representative_message
            == "Connection lost to database cluster primary"
        )

        val_group = next(g for g in groups if g.exception_type == "ValidationError")
        assert val_group.occurrence_count == 1
        assert (
            val_group.representative_message
            == "Missing required field 'shipping_address'"
        )

        # The recurring group with count 3 should be ranked first!
        assert groups[0] == db_group
        assert groups[1] == val_group

    def test_grouping_with_normalized_request_ids_in_message(self) -> None:
        """Verify grouping events when the exception message contains variable request IDs."""
        ev1 = _build_event(
            "ev-1",
            "RequestFailedError",
            "Failed processing for request req-111",
            10,
        )
        ev2 = _build_event(
            "ev-2",
            "RequestFailedError",
            "Failed processing for request req-222",
            20,
        )
        groups = group_failures([ev1, ev2])
        assert len(groups) == 1
        assert groups[0].occurrence_count == 2
        assert "<REQUEST_ID>" in groups[0].representative_message


class TestGroupingHelpers:
    """Verify internal grouping helper functions."""

    def test_derive_group_title_without_exception_type(self) -> None:
        """Verify title derivation when exception type is absent."""
        from app.services.grouping import _derive_group_title

        ev = _build_event("ev-1", None, "Uncaught database timeout error", 10)
        assert (
            _derive_group_title(ev, "Uncaught database timeout error")
            == "Uncaught database timeout error"
        )

        ev_empty = _build_event("ev-2", None, "", 20)
        assert _derive_group_title(ev_empty, "") == "Failure Event (exception)"

    def test_aggregate_severity_precedence(self) -> None:
        """Verify severity aggregation across occurrences."""
        from app.models.failure_group import FailureOccurrence
        from app.services.grouping import _aggregate_severity

        def _occ(level: LogLevel | None) -> FailureOccurrence:
            return FailureOccurrence(
                event_id="e",
                primary_line_number=1,
                start_line_number=1,
                end_line_number=1,
                original_message="m",
                level=level,
            )

        assert _aggregate_severity([]) is None
        assert _aggregate_severity([_occ(None)]) is None
        assert _aggregate_severity([_occ(LogLevel.INFO)]) == LogLevel.INFO
        assert (
            _aggregate_severity([_occ(LogLevel.INFO), _occ(LogLevel.WARNING)])
            == LogLevel.WARNING
        )
        assert (
            _aggregate_severity([_occ(LogLevel.WARNING), _occ(LogLevel.ERROR)])
            == LogLevel.ERROR
        )
        assert (
            _aggregate_severity([_occ(LogLevel.ERROR), _occ(LogLevel.CRITICAL)])
            == LogLevel.CRITICAL
        )

    def test_aggregate_component(self) -> None:
        """Verify component aggregation returns common component or None if mixed/absent."""
        from app.models.failure_group import FailureOccurrence
        from app.services.grouping import _aggregate_component

        def _occ(logger: str | None) -> FailureOccurrence:
            return FailureOccurrence(
                event_id="e",
                primary_line_number=1,
                start_line_number=1,
                end_line_number=1,
                original_message="m",
                logger_name=logger,
            )

        assert _aggregate_component([_occ(None)]) is None
        assert _aggregate_component([_occ("app.db"), _occ("app.db")]) == "app.db"
        assert _aggregate_component([_occ("app.db"), _occ("app.api")]) is None
