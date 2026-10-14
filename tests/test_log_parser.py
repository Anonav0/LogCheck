"""Integration and unit tests for the core LogParser engine."""

from app.models.failure_event import FailureEventType
from app.models.log_entry import LineCategory, LogLevel
from app.services.log_parser import LogParser, parse_log_text


class TestLogParserBasicParsing:
    """Verify fundamental line parsing, numbering, and edge cases."""

    def test_empty_input_returns_empty_result(self) -> None:
        """Verify empty string returns valid empty ParsingResult."""
        result = parse_log_text("")
        assert result.total_lines == 0
        assert result.entries == []
        assert result.failure_events == []
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.failure_event_count == 0

    def test_single_info_line(self) -> None:
        """Verify single line log parsing."""
        raw = "2026-10-14 08:30:00 [INFO] app.init: System starting"
        result = parse_log_text(raw)
        assert result.total_lines == 1
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.line_number == 1
        assert entry.raw_line == raw
        assert entry.level == LogLevel.INFO
        assert entry.logger_name == "app.init"
        assert entry.message == "System starting"
        assert result.error_count == 0
        assert result.failure_event_count == 0

    def test_log_parser_class_instance(self) -> None:
        """Verify direct use of LogParser class instance."""
        parser = LogParser()
        raw = "2026-10-14 08:30:00 [INFO] app: Direct instance test"
        result = parser.parse(raw)
        assert result.total_lines == 1
        assert result.entries[0].message == "Direct instance test"

    def test_line_order_preserved(self) -> None:
        """Verify multiple log lines preserve their exact order."""
        log = """2026-10-14 08:00:01 [INFO] app: Step 1
2026-10-14 08:00:02 [INFO] app: Step 2
2026-10-14 08:00:03 [INFO] app: Step 3"""
        result = parse_log_text(log)
        assert result.total_lines == 3
        for idx, entry in enumerate(result.entries, start=1):
            assert entry.line_number == idx
            assert f"Step {idx}" in entry.message

    def test_trailing_newline_does_not_shift_references(self) -> None:
        """Verify trailing newline does not introduce spurious empty entries or shift line numbers."""
        log = "2026-10-14 08:00:00 [INFO] app: Line 1\n"
        result = parse_log_text(log)
        assert result.total_lines == 1
        assert result.entries[0].line_number == 1

    def test_blank_lines_retain_correct_source_numbering(self) -> None:
        """Verify blank lines within a log are preserved with their exact 1-based line number."""
        log = """2026-10-14 08:00:01 [INFO] app: First

2026-10-14 08:00:03 [INFO] app: Third"""
        result = parse_log_text(log)
        assert result.total_lines == 3
        assert result.entries[0].line_number == 1
        assert result.entries[1].line_number == 2
        assert result.entries[1].raw_line == ""
        assert result.entries[2].line_number == 3

    def test_unicode_content_preserved(self) -> None:
        """Verify non-ASCII / Unicode characters are preserved accurately."""
        log = "2026-10-14 08:00:00 [INFO] app: Processed transaction for Café Münch €150.00 ✓"
        result = parse_log_text(log)
        entry = result.entries[0]
        assert "Café Münch €150.00 ✓" in entry.message

    def test_unknown_log_formats_do_not_crash(self) -> None:
        """Verify arbitrary text lines without known structure do not crash the parser."""
        log = """Header text from batch script
Random unstructured debug dump: hex=0xDEADBEEF
Completed successfully."""
        result = parse_log_text(log)
        assert result.total_lines == 3
        for entry in result.entries:
            assert entry.category == LineCategory.UNKNOWN


class TestLogParserFailureEventAssembly:
    """Verify logical failure event assembly and metric distinctions."""

    def test_standalone_error_creates_explicit_error_event(self) -> None:
        """Verify an explicit ERROR log without a traceback creates an explicit_error FailureEvent."""
        log = """2026-10-14 08:00:00 [INFO] app: Normal operation
2026-10-14 08:00:01 [ERROR] app.auth: Invalid token provided by client
2026-10-14 08:00:02 [INFO] app: Request finished"""

        result = parse_log_text(log)
        assert result.total_lines == 3
        assert result.error_count == 1
        assert result.failure_event_count == 1

        event = result.failure_events[0]
        assert event.event_type == FailureEventType.EXPLICIT_ERROR
        assert event.primary_line_number == 2
        assert event.message == "Invalid token provided by client"
        assert event.line_numbers == [2]

    def test_metrics_distinguish_error_lines_and_failure_events(self) -> None:
        """Verify total_lines, error_count, and failure_event_count are distinct metrics."""
        # 1 error line leading to 1 traceback spanning 6 lines
        log = """2026-10-14 08:30:05,432 [ERROR] app.database: Failed to acquire connection
Traceback (most recent call last):
  File "/srv/app/services/payment.py", line 142, in process_transaction
    async with db.transaction() as conn:
  File "/srv/app/database/connection.py", line 88, in transaction
    conn = await self.pool.acquire(timeout=5.0)
app.database.exceptions.ConnectionTimeoutError: Timed out waiting for connection"""

        result = parse_log_text(log)
        assert result.total_lines == 7
        assert result.error_count == 1  # Exactly 1 line has [ERROR]
        assert result.failure_event_count == 1  # Exactly 1 logical failure event
        assert result.stack_trace_line_count >= 5


class TestLogParserWithFixtures:
    """Verify parsing against all standard Phase 1 fixtures."""

    def test_parse_sample_application_log(
        self, sample_application_log_text: str
    ) -> None:
        """Verify sample_application.log parsing."""
        result = parse_log_text(sample_application_log_text)
        assert result.total_lines == len(sample_application_log_text.splitlines())
        assert result.warning_count == 1
        assert result.error_count == 1
        assert result.failure_event_count == 1

        event = result.failure_events[0]
        assert event.exception_type == "ConnectionTimeoutError"
        assert event.primary_line_number == 13
        assert event.start_line_number == 5

    def test_parse_recurring_failures_log(
        self, recurring_failures_log_text: str
    ) -> None:
        """Verify recurring_failures.log produces 4 distinct failure events."""
        result = parse_log_text(recurring_failures_log_text)
        assert result.total_lines == len(recurring_failures_log_text.splitlines())
        # 4 explicit error lines leading to 4 separate tracebacks
        assert result.error_count == 4
        assert result.failure_event_count == 4

        types = [e.exception_type for e in result.failure_events]
        assert types.count("DatabaseConnectionError") == 3
        assert types.count("ValidationError") == 1

    def test_parse_malformed_log(self, malformed_log_text: str) -> None:
        """Verify malformed.log parses safely without throwing unhandled exceptions."""
        result = parse_log_text(malformed_log_text)
        assert result.total_lines == 8
        # Ensure benign text with "error" did not inflate error_count
        assert result.error_count == 0
        assert result.failure_event_count == 0
