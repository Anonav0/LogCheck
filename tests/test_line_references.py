"""Tests for line reference formatting, range parsing, validation, and event linking."""

import pytest

from app.core.exceptions import InvalidLineReferenceError
from app.services.log_parser import parse_log_text
from app.utils.line_references import (
    format_line_ranges,
    format_line_reference,
    parse_line_reference,
    validate_line_numbers,
)


class TestLineReferenceUtilities:
    """Verify formatting, parsing, and validation of line references."""

    def test_format_single_line_reference(self) -> None:
        """Verify format_line_reference with single line returns 'L{n}'."""
        assert format_line_reference(1) == "L1"
        assert format_line_reference(42) == "L42"
        assert format_line_reference(15, 15) == "L15"

    def test_format_range_line_reference(self) -> None:
        """Verify format_line_reference with distinct range returns 'L{start}-L{end}'."""
        assert format_line_reference(12, 18) == "L12-L18"
        assert format_line_reference(1, 100) == "L1-L100"

    def test_format_invalid_lines_raise_error(self) -> None:
        """Verify non-positive or inverted line numbers raise InvalidLineReferenceError."""
        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(0)

        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(-5)

        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(10, 5)

        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(5, 0)

    def test_format_line_ranges_collapsed(self) -> None:
        """Verify contiguous lists of line numbers are collapsed cleanly."""
        assert format_line_ranges([]) == ""
        assert format_line_ranges([5]) == "L5"
        assert format_line_ranges([1, 2, 3]) == "L1-L3"
        assert format_line_ranges([1, 2, 3, 5, 7, 8]) == "L1-L3, L5, L7-L8"
        # Deduplication and unordered input
        assert format_line_ranges([8, 7, 5, 2, 1, 3, 2]) == "L1-L3, L5, L7-L8"

    def test_format_line_ranges_invalid_raises_error(self) -> None:
        """Verify format_line_ranges raises for negative line numbers."""
        with pytest.raises(InvalidLineReferenceError):
            format_line_ranges([1, 2, -3])

    def test_parse_line_reference_valid(self) -> None:
        """Verify parsing reference strings into list of (start, end) tuples."""
        assert parse_line_reference("") == []
        assert parse_line_reference("L12") == [(12, 12)]
        assert parse_line_reference("L12-L18") == [(12, 18)]
        assert parse_line_reference("L1-L3, L5, L7-L8") == [
            (1, 3),
            (5, 5),
            (7, 8),
        ]

    def test_parse_line_reference_invalid_format(self) -> None:
        """Verify invalid reference format strings raise InvalidLineReferenceError."""
        with pytest.raises(InvalidLineReferenceError):
            parse_line_reference("Line12")

        with pytest.raises(InvalidLineReferenceError):
            parse_line_reference("L18-L12")

    def test_validate_line_numbers(self) -> None:
        """Verify line numbers are validated against total source line count."""
        assert validate_line_numbers([], 10) is True
        assert validate_line_numbers([1, 5, 10], 10) is True
        assert validate_line_numbers([1, 11], 10) is False
        assert validate_line_numbers([0, 5], 10) is False
        assert validate_line_numbers([5], -1) is False


class TestEventReferenceIntegrity:
    """Verify failure events maintain exact, 1-based source line references."""

    def test_event_line_numbers_exist_in_source(
        self, sample_application_log_text: str
    ) -> None:
        """Verify every event in sample_application.log points to real source lines."""
        result = parse_log_text(sample_application_log_text)
        assert result.failure_event_count > 0

        for event in result.failure_events:
            assert validate_line_numbers(event.line_numbers, result.total_lines)
            assert event.start_line_number == event.line_numbers[0]
            assert event.end_line_number == event.line_numbers[-1]
            assert event.primary_line_number in event.line_numbers

            # Check that each referenced entry is linked back to event_id
            for ln in event.line_numbers:
                entry = result.entries[ln - 1]
                assert entry.line_number == ln
                assert entry.failure_event_id == event.event_id

    def test_event_line_numbers_ordered_and_one_based(
        self, recurring_failures_log_text: str
    ) -> None:
        """Verify line numbers across recurring failures remain monotonically ordered and 1-based."""
        result = parse_log_text(recurring_failures_log_text)
        assert len(result.failure_events) >= 3

        for event in result.failure_events:
            assert all(ln >= 1 for ln in event.line_numbers)
            assert event.line_numbers == sorted(event.line_numbers)
