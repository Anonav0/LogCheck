"""Tests for frontend display formatting, HTML escaping, and utility helpers."""

from __future__ import annotations

from frontend.utils import (
    build_source_html,
    compute_byte_size,
    compute_line_count,
    escape_html,
    format_duration_ms,
    format_fingerprint,
    format_line_number,
    severity_color,
    split_source_lines,
    validate_line_references,
)


def test_escape_html() -> None:
    """Test that HTML characters are escaped safely against XSS."""
    assert escape_html("") == ""
    assert escape_html("normal text") == "normal text"
    assert (
        escape_html("<script>alert('xss')</script>")
        == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
    )
    assert escape_html('foo & "bar"') == "foo &amp; &quot;bar&quot;"


def test_format_line_number() -> None:
    """Test line number padding."""
    assert format_line_number(5, total_lines=10) == "  5"
    assert format_line_number(42, total_lines=1000) == "  42"
    assert format_line_number(1234, total_lines=5000) == "1234"


def test_split_source_lines() -> None:
    """Test line splitting preserves blank lines and handles edge cases."""
    assert split_source_lines("") == []
    assert split_source_lines("line 1\nline 2\n\nline 4") == [
        "line 1",
        "line 2",
        "",
        "line 4",
    ]
    # Trailing newline should not add an extra empty line with splitlines
    assert split_source_lines("line 1\nline 2\n") == ["line 1", "line 2"]


def test_compute_byte_size_and_line_count() -> None:
    """Test UTF-8 byte counting and line counting."""
    assert compute_byte_size("") == 0
    assert compute_line_count("") == 0

    sample = "Hello World!\nLine 2 🚀\n"
    assert compute_byte_size(sample) == len(sample.encode("utf-8"))
    assert compute_line_count(sample) == 2


def test_format_duration_ms() -> None:
    """Test millisecond formatting for fast and slow processing times."""
    assert format_duration_ms(-5.0) == "0.00 ms"
    assert format_duration_ms(0.0) == "0.00 ms"
    assert format_duration_ms(45.678) == "45.68 ms"
    assert format_duration_ms(999.9) == "999.90 ms"
    assert format_duration_ms(1500.0) == "1.50 s"
    assert format_duration_ms(5432.1) == "5.43 s"


def test_format_fingerprint() -> None:
    """Test SHA-256 fingerprint truncation."""
    assert format_fingerprint("") == "—"
    assert format_fingerprint("short") == "short"
    full_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert format_fingerprint(full_sha) == "e3b0c44298fc…"
    assert format_fingerprint(full_sha, max_len=6) == "e3b0c4…"


def test_severity_color() -> None:
    """Test CSS color resolution for various severity levels."""
    assert severity_color(None) == "#495057"
    assert severity_color("ERROR") == "#d90429"
    assert severity_color("CRITICAL") == "#d90429"
    assert severity_color("WARNING") == "#e85d04"
    assert severity_color("INFO") == "#0077b6"
    assert severity_color("DEBUG") == "#6c757d"
    assert severity_color("unknown_level") == "#495057"


def test_validate_line_references() -> None:
    """Test filtering of 1-based source line numbers."""
    assert validate_line_references([], 10) == []
    assert validate_line_references([1, 2, 3], 0) == []
    assert validate_line_references([5, -1, 0, 10, 15, 3], total_lines=10) == [3, 5, 10]
    # Duplicates removed and sorted
    assert validate_line_references([5, 2, 5, 1, 2], total_lines=10) == [1, 2, 5]


def test_build_source_html_empty() -> None:
    """Test building HTML for empty lines."""
    html = build_source_html([])
    assert "No log lines available" in html


def test_build_source_html_with_highlights_and_escaping() -> None:
    """Test building HTML with primary, context, and AI highlights with escaping."""
    lines = [
        "2026-10-14 10:00:00 [INFO] app: Starting up <init>",
        "2026-10-14 10:00:01 [ERROR] app: Connection failed: host='127.0.0.1'",
        "    Traceback (most recent call last):",
        "      File 'db.py', line 45, in connect",
        "2026-10-14 10:00:02 [INFO] app: Shutting down",
    ]

    html = build_source_html(
        lines=lines,
        highlight_primary={2},
        highlight_context={3, 4},
        highlight_ai={2},
        focus_line=2,
        context_radius=2,
    )

    # Verify content was escaped
    assert "&lt;init&gt;" in html
    assert "<init>" not in html

    # Verify line numbers are present
    assert "1</span>" in html
    assert "2</span>" in html

    # Verify primary highlight styling (red) is applied
    assert "rgba(230, 57, 70" in html
