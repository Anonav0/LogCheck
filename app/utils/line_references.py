"""Utilities for formatting, parsing, and validating source line references."""

import re

from app.core.exceptions import InvalidLineReferenceError

_REF_PATTERN = re.compile(r"^L(\d+)(?:-L?(\d+))?$")


def split_source_lines(text: str) -> list[str]:
    """Split raw log text into canonical source lines without line terminators.

    Ensures consistent line numbering semantics across validation, parsing,
    and evidence verification.
    """
    if not text:
        return []
    return text.splitlines()


def format_line_reference(start_line: int, end_line: int | None = None) -> str:
    """Format a 1-based source line or line range into standard reference notation.

    Examples:
        format_line_reference(12) -> "L12"
        format_line_reference(12, 12) -> "L12"
        format_line_reference(12, 18) -> "L12-L18"
    """
    if start_line <= 0:
        raise InvalidLineReferenceError(
            f"Start line must be positive, got {start_line}"
        )
    if end_line is not None:
        if end_line <= 0:
            raise InvalidLineReferenceError(
                f"End line must be positive, got {end_line}"
            )
        if end_line < start_line:
            raise InvalidLineReferenceError(
                f"End line ({end_line}) cannot be less than start line ({start_line})"
            )
        if end_line == start_line:
            return f"L{start_line}"
        return f"L{start_line}-L{end_line}"
    return f"L{start_line}"


def format_line_ranges(line_numbers: list[int]) -> str:
    """Collapse a list of 1-based line numbers into contiguous range strings.

    Example:
        format_line_ranges([1, 2, 3, 5, 7, 8]) -> "L1-L3, L5, L7-L8"
    """
    if not line_numbers:
        return ""

    unique_sorted = sorted(set(line_numbers))
    for num in unique_sorted:
        if num <= 0:
            raise InvalidLineReferenceError(
                f"All line numbers must be positive, got {num}"
            )

    ranges: list[tuple[int, int]] = []
    start = unique_sorted[0]
    prev = unique_sorted[0]

    for num in unique_sorted[1:]:
        if num == prev + 1:
            prev = num
        else:
            ranges.append((start, prev))
            start = num
            prev = num
    ranges.append((start, prev))

    formatted_parts: list[str] = [
        format_line_reference(r_start, r_end) for r_start, r_end in ranges
    ]
    return ", ".join(formatted_parts)


def parse_line_reference(ref_str: str) -> list[tuple[int, int]]:
    """Parse reference string (e.g. 'L12', 'L12-L18', 'L1-L3, L5') into list of (start, end) tuples."""
    if not ref_str or not ref_str.strip():
        return []

    parts = [p.strip() for p in ref_str.split(",")]
    results: list[tuple[int, int]] = []

    for part in parts:
        match = _REF_PATTERN.match(part)
        if not match:
            raise InvalidLineReferenceError(
                f"Invalid line reference format: '{part}' in '{ref_str}'"
            )
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if end < start:
            raise InvalidLineReferenceError(
                f"End line ({end}) cannot be less than start line ({start}) in '{part}'"
            )
        results.append((start, end))

    return results


def validate_line_numbers(line_numbers: list[int], total_lines: int) -> bool:
    """Validate that all line numbers are strictly between 1 and total_lines inclusive."""
    if total_lines < 0:
        return False
    if not line_numbers:
        return True
    return all(1 <= num <= total_lines for num in line_numbers)
