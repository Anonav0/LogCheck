"""Tests for canonical line splitting semantics and edge cases across newlines and blank lines."""

import pytest

from app.core.exceptions import InvalidLineReferenceError
from app.services.evidence_validator import validate_parsing_result
from app.services.input_validator import validate_log_input
from app.services.log_parser import parse_log_text
from app.utils.line_references import (
    format_line_ranges,
    format_line_reference,
    parse_line_reference,
    split_source_lines,
    validate_line_numbers,
)


class TestCanonicalLineSplitting:
    """Verify canonical line-splitting consistency across validator, parser, and evidence checker."""

    @pytest.mark.parametrize(
        ("text", "expected_count"),
        [
            ("line 1", 1),
            ("line 1\n", 1),
            ("line 1\r\n", 1),
            ("line 1\nline 2", 2),
            ("line 1\nline 2\n", 2),
            ("line 1\n\nline 3", 3),
            ("line 1\n\nline 3\n\n", 4),
            ("\nline 2\nline 3", 3),
        ],
    )
    def test_split_source_lines_consistency(
        self, text: str, expected_count: int
    ) -> None:
        """Verify split_source_lines behaves canonically across all newline configurations."""
        lines = split_source_lines(text)
        assert len(lines) == expected_count

    def test_trailing_newline_consistency_across_components(self) -> None:
        """Verify trailing newlines produce identical line counts in validator, parser, and evidence checker."""
        log = "2026-10-14 10:00:00 [INFO] app: Ready\n2026-10-14 10:00:01 [INFO] app: Done\n"
        val_input = validate_log_input(log)
        parsed = parse_log_text(log)
        evidence_val = validate_parsing_result(log, parsed)

        assert val_input.line_count == 2
        assert parsed.total_lines == 2
        assert len(parsed.entries) == 2
        assert evidence_val.is_valid is True
        assert evidence_val.validated_lines_count == 2

    def test_multiple_trailing_newlines_consistency(self) -> None:
        """Verify multiple trailing newlines preserve empty trailing lines consistently."""
        log = "2026-10-14 10:00:00 [INFO] app: Step 1\n\n\n"
        val_input = validate_log_input(log)
        parsed = parse_log_text(log)
        evidence_val = validate_parsing_result(log, parsed)

        # "line\n\n\n".splitlines() -> ['line', '', ''] -> 3 lines
        assert val_input.line_count == 3
        assert parsed.total_lines == 3
        assert len(parsed.entries) == 3
        assert evidence_val.is_valid is True

    def test_leading_blank_lines_do_not_shift_subsequent_line_numbers(self) -> None:
        """Verify leading blank line puts actual first log statement at line 2."""
        log = "\n2026-10-14 10:00:00 [ERROR] app: Error statement"
        val_input = validate_log_input(log)
        parsed = parse_log_text(log)

        assert val_input.line_count == 2
        assert parsed.entries[0].line_number == 1
        assert parsed.entries[0].raw_line == ""
        assert parsed.entries[1].line_number == 2
        assert parsed.entries[1].level.value == "ERROR"
        assert parsed.failure_events[0].primary_line_number == 2

        evidence_val = validate_parsing_result(log, parsed)
        assert evidence_val.is_valid is True

    def test_multiline_unicode_preserves_line_indexing(self) -> None:
        """Verify complex Unicode and multi-byte characters do not disrupt line numbers."""
        log = "2026-10-14 [INFO] 🚀 Launch sequence\n2026-10-14 [INFO] ✨ Star tracker online\n2026-10-14 [INFO] 🛰️ Telemetry ok"
        parsed = parse_log_text(log)
        assert parsed.total_lines == 3
        assert parsed.entries[1].line_number == 2
        assert "✨ Star tracker online" in parsed.entries[1].raw_line

        evidence_val = validate_parsing_result(log, parsed)
        assert evidence_val.is_valid is True


class TestLineReferenceUtilityEdgeCases:
    """Verify edge cases in format_line_reference, format_line_ranges, and parse_line_reference."""

    def test_zero_or_negative_line_numbers_rejected(self) -> None:
        """Verify zero and negative line numbers are rejected."""
        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(0)

        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(-1, 5)

        with pytest.raises(InvalidLineReferenceError):
            format_line_ranges([0, 1, 2])

        with pytest.raises(InvalidLineReferenceError):
            format_line_ranges([-5])

    def test_reversed_line_range_rejected(self) -> None:
        """Verify end_line < start_line is rejected."""
        with pytest.raises(InvalidLineReferenceError):
            format_line_reference(10, 5)

        with pytest.raises(InvalidLineReferenceError):
            parse_line_reference("L20-L10")

    def test_validate_line_numbers_boundaries(self) -> None:
        """Verify validate_line_numbers against edge values."""
        assert validate_line_numbers([], 100) is True
        assert validate_line_numbers([1], 1) is True
        assert validate_line_numbers([2], 1) is False
        assert validate_line_numbers([0], 1) is False
        assert validate_line_numbers([1, 2, 3], -5) is False
