"""Boundary limits, evidence integrity, and performance reliability tests for Phase 8.

Verifies:
- Exact byte size boundary (1 MiB: 1,048,576 valid, 1,048,577 rejected)
- Exact line count boundary (20,000 valid, 20,001 rejected)
- Exact line length boundary (16,384 characters valid, 16,385 rejected)
- Multi-byte UTF-8 character alignment near size limit
- Strict rejection of invalid UTF-8 and non-text uploads
- Evidence validation invariants: invalid lines, mismatched excerpts, line range errors
- Repeated failure scalability under 500 instances
- Deterministic processing performance benchmark under 2.0s
"""

import time

import pytest

from app.core.config import Settings
from app.core.exceptions import InputValidationError
from app.services.evidence_validator import (
    validate_analysis_result,
    validate_parsing_result,
)
from app.services.grouping import analyze_failures
from app.services.input_validator import validate_log_file_bytes, validate_log_input
from app.services.log_parser import parse_log_text


class TestInputBoundaryLimits:
    """Tests checking exact byte, line, and character limits."""

    def test_byte_limit_exact_boundary(self) -> None:
        """1,048,576 bytes is valid; 1,048,577 bytes must raise InputValidationError."""
        settings = Settings(MAX_LOG_SIZE_BYTES=1_048_576, _env_file=None)

        # 1. Exactly 1 MiB formatted in 100-byte lines (99 chars + \n)
        chunk = "A" * 99 + "\n"
        # 10,485 chunks * 100 = 1,048,500 bytes. Remainder = 76 bytes (75 chars + \n)
        exact_payload = (chunk * 10_485) + ("A" * 75 + "\n")
        assert len(exact_payload.encode("utf-8")) == 1_048_576
        val = validate_log_input(exact_payload, settings)
        assert val.byte_size == 1_048_576

        # 2. 1 MiB + 1 byte
        over_payload = exact_payload + "B"
        assert len(over_payload.encode("utf-8")) == 1_048_577
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(over_payload, settings)
        assert exc_info.value.code == "LOG_TOO_LARGE"
        assert exc_info.value.actual == 1_048_577
        assert exc_info.value.limit == 1_048_576

    def test_line_count_exact_boundary(self) -> None:
        """20,000 lines is valid; 20,001 lines must raise InputValidationError."""
        settings = Settings(MAX_LOG_LINES=20_000, _env_file=None)

        # 1. Exactly 20,000 lines
        lines_20k = "\n".join(["2026-10-15 10:00:00 INFO app - Tick"] * 20_000)
        val = validate_log_input(lines_20k, settings)
        assert val.line_count == 20_000

        # 2. 20,001 lines
        lines_20k_plus_1 = lines_20k + "\n2026-10-15 10:00:01 INFO app - Overflow"
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(lines_20k_plus_1, settings)
        assert exc_info.value.code == "TOO_MANY_LOG_LINES"
        assert exc_info.value.actual == 20_001
        assert exc_info.value.limit == 20_000

    def test_line_length_exact_boundary(self) -> None:
        """Line of 16,384 characters is valid; 16,385 characters must raise InputValidationError."""
        settings = Settings(MAX_LOG_LINE_LENGTH=16_384, _env_file=None)

        # Exactly 16,384 chars
        exact_line = "2026-10-15 10:00:00 INFO app - " + "X" * (16_384 - 31)
        assert len(exact_line) == 16_384
        val = validate_log_input(exact_line, settings)
        assert val.line_count == 1

        # 16,385 chars
        over_line = exact_line + "Y"
        assert len(over_line) == 16_385
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(over_line, settings)
        assert exc_info.value.code == "LOG_LINE_TOO_LONG"
        assert exc_info.value.actual == 16_385
        assert exc_info.value.limit == 16_384

    def test_multibyte_utf8_near_byte_boundary(self) -> None:
        """Ensure multi-byte characters (e.g. 4-byte emojis) are evaluated by byte size, not char count."""
        settings = Settings(MAX_LOG_SIZE_BYTES=100, _env_file=None)

        # 25 emojis = 100 bytes (valid)
        valid_emojis = "🚀" * 25
        assert len(valid_emojis) == 25  # 25 characters
        assert len(valid_emojis.encode("utf-8")) == 100  # 100 bytes
        val = validate_log_input(valid_emojis, settings)
        assert val.byte_size == 100

        # 26 emojis = 104 bytes (exceeds 100 byte limit)
        over_emojis = "🚀" * 26
        assert len(over_emojis.encode("utf-8")) == 104
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input(over_emojis, settings)
        assert exc_info.value.code == "LOG_TOO_LARGE"
        assert exc_info.value.actual == 104

    def test_invalid_utf8_bytes_rejected(self) -> None:
        """Invalid non-UTF8 binary byte sequence must be rejected."""
        corrupt_bytes = b"\xff\xfe\xfd\x80\x81invalid binary stream"
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_file_bytes(corrupt_bytes)
        assert exc_info.value.code == "INVALID_ENCODING"

    def test_empty_input_rejected(self) -> None:
        with pytest.raises(InputValidationError) as exc_info:
            validate_log_input("   \n\t  ")
        assert exc_info.value.code == "EMPTY_LOG_INPUT"


class TestEvidenceIntegrityRigorous:
    """Tests ensuring evidence validator catches corrupt or fabricated references."""

    def test_out_of_bounds_line_reference_detected(self) -> None:
        raw = "Line 1\nLine 2\nLine 3"
        parsed = parse_log_text(raw)
        # Corrupt an entry line number
        parsed.entries[0].line_number = 999
        res = validate_parsing_result(raw, parsed)
        assert not res.is_valid
        assert any(
            "LINE_OUT_OF_RANGE" in err.code or "NON_MONOTONIC" in err.code
            for err in res.errors
        )

    def test_mismatched_source_line_detected(self) -> None:
        raw = "Line 1: authentic\nLine 2: data"
        parsed = parse_log_text(raw)
        # Corrupt raw_line content in model
        parsed.entries[0].raw_line = "Line 1: tampered"
        res = validate_parsing_result(raw, parsed)
        assert not res.is_valid
        assert any("CONTENT_MISMATCH" in err.code for err in res.errors)

    def test_corrupted_group_occurrences_count_detected(self) -> None:
        raw = "2026-10-15 10:00:00 ERROR app - DB error: timeout"
        parsed = parse_log_text(raw)
        grouped = analyze_failures(parsed)

        # Corrupt occurrence count vs occurrences list
        grouped.failure_groups[0].occurrence_count = 99
        res = validate_analysis_result(raw, grouped)
        assert not res.is_valid
        assert any("COUNT_MISMATCH" in err.code for err in res.errors)

    def test_reversed_event_line_range_detected(self) -> None:
        raw = "2026-10-15 10:00:00 ERROR app - Error message"
        parsed = parse_log_text(raw)
        assert len(parsed.failure_events) == 1
        # Invert start and end lines
        parsed.failure_events[0].start_line_number = 10
        parsed.failure_events[0].end_line_number = 2
        res = validate_parsing_result(raw, parsed)
        assert not res.is_valid
        assert any("REVERSED_LINE_RANGE" in err.code for err in res.errors)


class TestScalabilityAndBenchmark:
    """Scalability test with repeated failures and throughput benchmark."""

    def test_500_repeated_failures_scalability(self) -> None:
        """Process 500 repeated failures: verify clustering and memory stability."""
        error_lines = []
        for i in range(500):
            error_lines.append(
                f"2026-10-15 10:{i // 60:02d}:{i % 60:02d} ERROR worker - PoolTimeoutError: Timeout waiting for pool connection [req-{i}]"
            )
        raw_log = "\n".join(error_lines)

        start_time = time.perf_counter()
        parsed = parse_log_text(raw_log)
        grouped = analyze_failures(parsed)
        duration = time.perf_counter() - start_time

        # All 500 should group into 1 failure group
        assert len(grouped.failure_groups) == 1
        assert grouped.failure_groups[0].occurrence_count == 500
        assert grouped.metrics.total_failure_events == 500
        assert grouped.metrics.repeated_failure_groups == 1

        # Processing 500 lines through parsing and grouping must complete quickly
        assert duration < 2.0, f"Expected < 2.0s for 500 failures, took {duration:.3f}s"

    def test_1000_line_mixed_log_benchmark(self) -> None:
        """1,000 lines mixed log parsing, grouping, and evidence validation benchmark."""
        exceptions = [
            "DatabaseError",
            "TimeoutError",
            "AuthError",
            "NetworkError",
            "ConfigError",
        ]
        lines = []
        for i in range(1000):
            if i % 10 == 0:
                exc = exceptions[(i // 10) % 5]
                lines.append(
                    f"2026-10-15 10:00:00 ERROR app.service - {exc}: Critical failure"
                )
            else:
                lines.append(f"2026-10-15 10:00:00 INFO app - Heartbeat tick {i}")
        raw_log = "\n".join(lines)

        start = time.perf_counter()
        parsed = parse_log_text(raw_log)
        grouped = analyze_failures(parsed)
        p_val = validate_parsing_result(raw_log, parsed)
        g_val = validate_analysis_result(raw_log, grouped)
        duration = time.perf_counter() - start

        assert p_val.is_valid
        assert g_val.is_valid
        assert len(grouped.failure_groups) == 5
        assert duration < 2.0, f"Benchmark exceeded 2.0s: {duration:.3f}s"
